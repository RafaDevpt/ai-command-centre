"""
Login local: argon2id, sessões por cookie, CSRF e limite de tentativas.

- O cookie leva um token aleatório; na BD fica só o SHA-256 (uma fuga da BD
  não dá sessões válidas).
- Pedidos que alteram estado (POST/PUT/PATCH/DELETE) exigem o cabeçalho
  X-CSRF-Token igual ao da sessão. SameSite=Strict é a segunda barreira.
- 5 falhas em 15 min por IP ou por utilizador → 429 durante essa janela.

Created by Redfox using Claude
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, WebSocket
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import sessao
from .models import AuditLog, LoginAttempt, LoginSession, User

COOKIE = "aicc_sessao"
DURACAO = timedelta(days=7)
JANELA_FALHAS = timedelta(minutes=15)
MAX_FALHAS = 5
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}

_hasher = PasswordHasher()   # argon2id com os parâmetros recomendados pela biblioteca
#: Usado quando o utilizador não existe: o tempo de resposta fica igual.
HASH_FICTICIO = _hasher.hash("utilizador-que-nao-existe")


def agora() -> datetime:
    return datetime.now(UTC)


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)


def senha_certa(hash_: str, senha: str) -> bool:
    try:
        return _hasher.verify(hash_, senha)
    except (VerificationError, InvalidHashError):
        return False


def validar_senha_nova(senha: str) -> None:
    if len(senha) < 12:
        raise HTTPException(400, "A palavra-passe tem de ter pelo menos 12 caracteres.")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def auditar(s: AsyncSession, actor: str, action: str, **detail) -> None:
    s.add(AuditLog(actor=actor, action=action, detail=detail))


async def bloqueado(s: AsyncSession, chaves: list[str]) -> bool:
    desde = agora() - JANELA_FALHAS
    for chave in chaves:
        n = await s.scalar(select(func.count()).select_from(LoginAttempt)
                           .where(LoginAttempt.key == chave, LoginAttempt.created_at >= desde))
        if (n or 0) >= MAX_FALHAS:
            return True
    return False


async def criar_sessao(s: AsyncSession, user: User, resposta: Response, seguro: bool, ua: str) -> LoginSession:
    token = secrets.token_urlsafe(32)
    ls = LoginSession(token_hash=_hash_token(token), csrf_token=secrets.token_urlsafe(32), user_id=user.id,
                      expires_at=agora() + DURACAO, user_agent=ua[:200])
    s.add(ls)
    resposta.set_cookie(COOKIE, token, max_age=int(DURACAO.total_seconds()), httponly=True,
                        samesite="strict", secure=seguro, path="/")
    return ls


async def sessao_do_pedido(s: AsyncSession, token: str | None) -> tuple[LoginSession, User] | None:
    if not token:
        return None
    ls = await s.scalar(select(LoginSession).where(LoginSession.token_hash == _hash_token(token)))
    if ls is None or _utc(ls.expires_at) < agora():
        return None
    user = await s.get(User, ls.user_id)
    if user is None:
        return None
    if agora() - _utc(ls.last_seen) > timedelta(minutes=5):
        ls.last_seen = agora()
        await s.commit()
    return ls, user


class Autenticado:
    def __init__(self, user: User, login: LoginSession) -> None:
        self.user, self.login = user, login


async def autenticado(pedido: Request, s: AsyncSession = Depends(sessao)) -> Autenticado:
    """Dependência para todas as rotas protegidas: sessão válida e, se o método altera estado, CSRF."""
    r = await sessao_do_pedido(s, pedido.cookies.get(COOKIE))
    if r is None:
        raise HTTPException(401, "Sessão inválida ou expirada.")
    ls, user = r
    if pedido.method not in METODOS_SEGUROS:
        enviado = pedido.headers.get("X-CSRF-Token", "")
        if not enviado or not hmac.compare_digest(enviado, ls.csrf_token):
            raise HTTPException(403, "Pedido recusado (CSRF).")
    return Autenticado(user, ls)


async def autenticado_ws(ws: WebSocket, s: AsyncSession) -> Autenticado | None:
    """WebSocket: cookie + origem igual ao anfitrião (os browsers não aplicam CORS a WS)."""
    origem = ws.headers.get("origin", "")
    anfitriao = ws.headers.get("host", "")
    if origem and origem.split("://", 1)[-1] != anfitriao:
        return None
    r = await sessao_do_pedido(s, ws.cookies.get(COOKIE))
    return Autenticado(r[1], r[0]) if r else None


async def limpar_expiradas(s: AsyncSession) -> None:
    await s.execute(delete(LoginSession).where(LoginSession.expires_at < agora()))
    await s.execute(delete(LoginAttempt).where(LoginAttempt.created_at < agora() - timedelta(days=1)))
