"""Rotas de autenticação e conta. Created by Redfox using Claude"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import sessao
from .models import LoginAttempt, LoginSession, User
from .seguranca import (COOKIE, HASH_FICTICIO, Autenticado, auditar, autenticado, bloqueado, criar_sessao, hash_senha,
                        limpar_expiradas, senha_certa, validar_senha_nova)

r = APIRouter(prefix="/api/auth", tags=["auth"])


class Credenciais(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class MudarSenha(BaseModel):
    atual: str = Field(min_length=1, max_length=256)
    nova: str = Field(min_length=12, max_length=256)


def _ip(pedido: Request) -> str:
    return pedido.client.host if pedido.client else "?"


def _https(pedido: Request) -> bool:
    return pedido.url.scheme == "https" or pedido.headers.get("x-forwarded-proto") == "https"


@r.post("/login")
async def login(dados: Credenciais, pedido: Request, resposta: Response, s: AsyncSession = Depends(sessao)):
    chaves = [f"ip:{_ip(pedido)}", f"user:{dados.username.lower()}"]
    if await bloqueado(s, chaves):
        raise HTTPException(429, "Demasiadas tentativas. Tente de novo dentro de 15 minutos.")
    user = await s.scalar(select(User).where(User.username == dados.username))
    # Verifica sempre um hash (mesmo sem utilizador) para não revelar quem existe pelo tempo.
    ok = senha_certa(user.password_hash if user else HASH_FICTICIO, dados.password) and user is not None
    if not ok:
        for k in chaves:
            s.add(LoginAttempt(key=k))
        await auditar(s, dados.username[:64], "login-falhado", ip=_ip(pedido))
        await s.commit()
        raise HTTPException(401, "Utilizador ou palavra-passe errados.")
    await s.execute(delete(LoginAttempt).where(LoginAttempt.key.in_(chaves)))
    await limpar_expiradas(s)
    ls = await criar_sessao(s, user, resposta, _https(pedido), pedido.headers.get("user-agent", ""))
    await auditar(s, user.username, "login", ip=_ip(pedido))
    await s.commit()
    return {"username": user.username, "csrf": ls.csrf_token}


@r.get("/me")
async def eu(a: Autenticado = Depends(autenticado)):
    return {"username": a.user.username, "is_admin": a.user.is_admin, "csrf": a.login.csrf_token}


@r.post("/logout")
async def logout(resposta: Response, a: Autenticado = Depends(autenticado), s: AsyncSession = Depends(sessao)):
    await s.execute(delete(LoginSession).where(LoginSession.id == a.login.id))
    await auditar(s, a.user.username, "logout")
    await s.commit()
    resposta.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@r.post("/password")
async def mudar_senha(dados: MudarSenha, a: Autenticado = Depends(autenticado), s: AsyncSession = Depends(sessao)):
    user = await s.get(User, a.user.id)
    if not senha_certa(user.password_hash, dados.atual):
        raise HTTPException(400, "A palavra-passe actual está errada.")
    validar_senha_nova(dados.nova)
    user.password_hash = hash_senha(dados.nova)
    # Termina todas as outras sessões.
    await s.execute(delete(LoginSession).where(LoginSession.user_id == user.id, LoginSession.id != a.login.id))
    await auditar(s, user.username, "senha-alterada")
    await s.commit()
    return {"ok": True}


@r.get("/sessions")
async def sessoes_login(a: Autenticado = Depends(autenticado), s: AsyncSession = Depends(sessao)):
    linhas = (await s.scalars(select(LoginSession).where(LoginSession.user_id == a.user.id)
                              .order_by(LoginSession.last_seen.desc()))).all()
    return [{"id": x.id, "actual": x.id == a.login.id, "criada": x.created_at, "ultima": x.last_seen,
             "dispositivo": x.user_agent} for x in linhas]


@r.post("/sessions/terminar-outras")
async def terminar_outras(a: Autenticado = Depends(autenticado), s: AsyncSession = Depends(sessao)):
    await s.execute(delete(LoginSession).where(LoginSession.user_id == a.user.id, LoginSession.id != a.login.id))
    await auditar(s, a.user.username, "sessoes-terminadas")
    await s.commit()
    return {"ok": True}
