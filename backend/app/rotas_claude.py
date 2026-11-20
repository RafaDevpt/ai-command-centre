"""
Claude como aplicação externa oficial. Este servidor NÃO fala com o Claude:
sem automação do claude.ai, sem cookies, sem tokens, sem proxies. Aqui só:
- importar a exportação oficial (Definições → Privacidade → Exportar dados no
  claude.ai; ficheiro .zip ou conversations.json) como sessões só de leitura;
- registar à mão uma sessão externa (título, ligação claude.ai, notas).

Created by Redfox using Claude
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import sessao
from .models import ChatSession, Message, Project
from .seguranca import Autenticado, agora, auditar, autenticado

r = APIRouter(prefix="/api/claude", tags=["claude"])
MAX_ENVIO = 100 * 1024 * 1024
MAX_JSON = 300 * 1024 * 1024
FORNECEDOR = "claude-externo"


class Registo(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)
    ligacao: str | None = Field(default=None, max_length=300, pattern=r"^https://claude\.ai/[\w\-/?=&.#]*$")
    notas: str = Field(default="", max_length=50000)
    projecto_id: str | None = None


def _data(v) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _texto(m: dict) -> str:
    if isinstance(m.get("text"), str) and m["text"].strip():
        return m["text"]
    partes = [c.get("text", "") for c in m.get("content") or [] if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(p for p in partes if p)


def _ler_exportacao(nome: str, dados: bytes) -> list:
    if nome.lower().endswith(".zip") or dados[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(dados))
        except zipfile.BadZipFile as exc:
            raise HTTPException(400, "ZIP inválido.") from exc
        info = next((i for i in z.infolist() if i.filename.rsplit("/", 1)[-1] == "conversations.json"), None)
        if info is None:
            raise HTTPException(400, "O ZIP não tem conversations.json (é a exportação oficial do claude.ai?).")
        if info.file_size > MAX_JSON:
            raise HTTPException(413, "conversations.json demasiado grande.")
        dados = z.read(info)
    try:
        conversas = json.loads(dados)
    except ValueError as exc:
        raise HTTPException(400, "JSON inválido.") from exc
    if not isinstance(conversas, list):
        raise HTTPException(400, "Formato inesperado: era esperada uma lista de conversas.")
    return conversas


@r.get("/status")
async def estado(s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    n = await s.scalar(select(func.count()).select_from(ChatSession).where(ChatSession.provider == FORNECEDOR))
    ultima = await s.scalar(select(func.max(ChatSession.created_at)).where(ChatSession.provider == FORNECEDOR))
    return {"externo": True, "url": "https://claude.ai", "sessoes_importadas": n or 0,
            "ultima_importacao": ultima.isoformat() if ultima else None,
            "nota": "Aplicação oficial separada. O estado da conta não é consultado por este servidor."}


@r.post("/import")
async def importar(ficheiro: UploadFile, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    dados = await ficheiro.read(MAX_ENVIO + 1)
    if len(dados) > MAX_ENVIO:
        raise HTTPException(413, "Ficheiro maior do que 100 MB.")
    conversas = _ler_exportacao(ficheiro.filename or "", dados)
    existentes = set((await s.scalars(select(ChatSession.external_id).where(ChatSession.provider == FORNECEDOR))).all())
    novas = repetidas = mensagens = 0
    for c in conversas:
        if not isinstance(c, dict):
            continue
        uid = str(c.get("uuid") or "")[:120]
        if uid and uid in existentes:
            repetidas += 1
            continue
        msgs = [m for m in c.get("chat_messages") or [] if isinstance(m, dict) and _texto(m)]
        sess = ChatSession(title=(c.get("name") or "Conversa do Claude")[:200], provider=FORNECEDOR, model="claude.ai",
                           status="externa", external_id=uid or None)
        criada = _data(c.get("created_at"))
        if criada:
            sess.created_at = criada
        sess.last_activity = _data(c.get("updated_at")) or criada or agora()
        s.add(sess)
        await s.flush()
        for m in msgs:
            papel = "user" if m.get("sender") == "human" else "assistant"
            msg = Message(session_id=sess.id, role=papel, content=_texto(m)[:200_000],
                          provider=None if papel == "user" else FORNECEDOR, model=None if papel == "user" else "claude.ai")
            if (d := _data(m.get("created_at"))):
                msg.created_at = d
            s.add(msg)
            mensagens += 1
        existentes.add(uid)
        novas += 1
    await auditar(s, u.user.username, "claude-importado", novas=novas, repetidas=repetidas)
    await s.commit()
    return {"novas": novas, "repetidas": repetidas, "mensagens": mensagens}


@r.post("/sessions")
async def registar(d: Registo, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    if d.projecto_id and not await s.get(Project, d.projecto_id):
        raise HTTPException(404, "Projecto não encontrado.")
    sess = ChatSession(title=d.titulo, provider=FORNECEDOR, model="claude.ai", status="externa",
                       project_id=d.projecto_id, external_id=d.ligacao)
    s.add(sess)
    await s.flush()
    corpo = "\n\n".join(x for x in (f"Ligação: {d.ligacao}" if d.ligacao else "", d.notas) if x) or "(sem notas)"
    s.add(Message(session_id=sess.id, role="user", content=corpo))
    await auditar(s, u.user.username, "claude-sessao-registada", sessao=sess.id)
    await s.commit()
    return {"id": sess.id}
