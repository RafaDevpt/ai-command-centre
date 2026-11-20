"""Sessões de conversa, modelos, anexos e o WebSocket de conversa. Created by Redfox using Claude"""

from __future__ import annotations

import asyncio
import hmac

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import fornecedores, ollama
from .anexos import guardar
from .conversa import responder
from .db import sessao
from .models import ChatSession, Message, Project
from .seguranca import Autenticado, auditar, autenticado, autenticado_ws

r = APIRouter(prefix="/api", tags=["conversa"])
FORNECEDORES_CONVERSA = {"ollama", "codex"}


class NovaSessao(BaseModel):
    fornecedor: str = Field(pattern="^(ollama|codex)$")
    modelo: str = Field(min_length=1, max_length=120)
    projecto_id: str | None = None
    titulo: str | None = Field(default=None, max_length=200)


class AlterarSessao(BaseModel):
    titulo: str | None = Field(default=None, max_length=200)
    projecto_id: str | None = None
    estado: str | None = Field(default=None, pattern="^(activa|arquivada)$")


def _sessao_json(c: ChatSession) -> dict:
    return {"id": c.id, "titulo": c.title, "fornecedor": c.provider, "modelo": c.model,
            "projecto_id": c.project_id, "estado": c.status, "criada": c.created_at, "ultima": c.last_activity,
            "retomavel": c.status != "externa"}


@r.get("/models")
async def listar_modelos(a: Autenticado = Depends(autenticado)):
    return await fornecedores.modelos()


@r.get("/models/ollama/{nome:path}")
async def detalhes_modelo(nome: str, a: Autenticado = Depends(autenticado)):
    return await ollama.detalhes(nome)


@r.get("/sessions")
async def listar(q: str | None = Query(None, max_length=200), projecto: str | None = None,
                 fornecedor: str | None = None, estado: str | None = None, limite: int = Query(50, le=200),
                 a: Autenticado = Depends(autenticado), s: AsyncSession = Depends(sessao)):
    consulta = select(ChatSession)
    if q:
        padrao = f"%{q}%"
        com_texto = select(Message.session_id).where(Message.content.ilike(padrao))
        consulta = consulta.where(or_(ChatSession.title.ilike(padrao), ChatSession.id.in_(com_texto)))
    if projecto:
        consulta = consulta.where(ChatSession.project_id == projecto)
    if fornecedor:
        consulta = consulta.where(ChatSession.provider == fornecedor)
    if estado:
        consulta = consulta.where(ChatSession.status == estado)
    linhas = (await s.scalars(consulta.order_by(ChatSession.last_activity.desc()).limit(limite))).all()
    return [_sessao_json(c) for c in linhas]


@r.post("/sessions")
async def criar(dados: NovaSessao, a: Autenticado = Depends(autenticado), s: AsyncSession = Depends(sessao)):
    if dados.projecto_id and not await s.get(Project, dados.projecto_id):
        raise HTTPException(404, "Projecto não encontrado.")
    c = ChatSession(provider=dados.fornecedor, model=dados.modelo, project_id=dados.projecto_id,
                    title=dados.titulo or "Nova conversa")
    s.add(c)
    await auditar(s, a.user.username, "sessao-criada", fornecedor=c.provider, modelo=c.model)
    await s.commit()
    return _sessao_json(c)


@r.get("/sessions/{sid}")
async def obter(sid: str, a: Autenticado = Depends(autenticado), s: AsyncSession = Depends(sessao)):
    c = await s.get(ChatSession, sid)
    if c is None:
        raise HTTPException(404, "Sessão não encontrada.")
    msgs = (await s.scalars(select(Message).where(Message.session_id == sid).order_by(Message.id))).all()
    return {**_sessao_json(c), "mensagens": [
        {"id": m.id, "papel": m.role, "texto": m.content, "fornecedor": m.provider, "modelo": m.model,
         "anexos": [{"id": x["id"], "nome": x.get("nome")} for x in (m.attachments or [])], "criada": m.created_at}
        for m in msgs]}


@r.patch("/sessions/{sid}")
async def alterar(sid: str, dados: AlterarSessao, a: Autenticado = Depends(autenticado),
                  s: AsyncSession = Depends(sessao)):
    c = await s.get(ChatSession, sid)
    if c is None:
        raise HTTPException(404, "Sessão não encontrada.")
    if dados.titulo is not None:
        c.title = dados.titulo
    if dados.projecto_id is not None:
        if dados.projecto_id and not await s.get(Project, dados.projecto_id):
            raise HTTPException(404, "Projecto não encontrado.")
        c.project_id = dados.projecto_id or None
    if dados.estado is not None and c.status != "externa":
        c.status = dados.estado
    await s.commit()
    return _sessao_json(c)


@r.post("/attachments")
async def anexar(ficheiro: UploadFile = File(...), a: Autenticado = Depends(autenticado)):
    return await guardar(ficheiro)


@r.websocket("/ws/chat")
async def ws_conversa(ws: WebSocket):
    """
    Protocolo (JSON): cliente envia {"tipo":"enviar","csrf","sessao_id","texto","anexos":[...]};
    o servidor responde com {"tipo":"delta"}, {"tipo":"aprovacao"}, {"tipo":"fim"} ou {"tipo":"erro"}.
    {"tipo":"parar"} interrompe a resposta em curso.
    """
    async for s in sessao():
        auth = await autenticado_ws(ws, s)
        if auth is None:
            await ws.close(code=4401)
            return
        await ws.accept()
        tarefa: asyncio.Task | None = None

        async def correr(sessao_conversa: ChatSession, texto: str, anexos: list[dict]):
            try:
                async for e in responder(s, sessao_conversa, texto, anexos):
                    await ws.send_json(e)
            except Exception as exc:  # noqa: BLE001
                await ws.send_json({"tipo": "erro", "texto": f"{type(exc).__name__}"})

        try:
            while True:
                msg = await ws.receive_json()
                if not hmac.compare_digest(str(msg.get("csrf", "")), auth.login.csrf_token):
                    await ws.send_json({"tipo": "erro", "texto": "CSRF inválido."})
                    continue
                if msg.get("tipo") == "parar":
                    if tarefa and not tarefa.done():
                        tarefa.cancel()
                        await ws.send_json({"tipo": "parado"})
                    continue
                if msg.get("tipo") != "enviar":
                    continue
                if tarefa and not tarefa.done():
                    await ws.send_json({"tipo": "erro", "texto": "Já há uma resposta em curso."})
                    continue
                c = await s.get(ChatSession, str(msg.get("sessao_id", "")))
                texto = str(msg.get("texto", ""))[:20000]
                if c is None or not texto.strip():
                    await ws.send_json({"tipo": "erro", "texto": "Sessão ou texto em falta."})
                    continue
                if c.status == "externa":
                    await ws.send_json({"tipo": "erro", "texto": "Sessão externa: só leitura."})
                    continue
                anexos = [x for x in msg.get("anexos", []) if isinstance(x, dict) and "id" in x][:5]
                tarefa = asyncio.create_task(correr(c, texto, anexos))
        except WebSocketDisconnect:
            if tarefa and not tarefa.done():
                tarefa.cancel()
