"""
Codex: estado da conta, login oficial por código de dispositivo e logout.
Nada aqui devolve tokens; o email vai mascarado. Created by Redfox using Claude
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from .codex import ErroCodex, gestor
from .db import sessao
from .seguranca import Autenticado, auditar, autenticado

r = APIRouter(prefix="/api/codex", tags=["codex"])


class Cancelar(BaseModel):
    login_id: str = Field(min_length=1, max_length=100)


@r.get("/status")
async def estado(_: Autenticado = Depends(autenticado)):
    return await gestor().estado()


@r.post("/login")
async def login(s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    try:
        dados = await gestor().iniciar_login()
    except ErroCodex as exc:
        raise HTTPException(503, str(exc)) from exc
    await auditar(s, u.user.username, "codex-login-iniciado")
    await s.commit()
    return dados


@r.post("/login/cancel")
async def cancelar(c: Cancelar, _: Autenticado = Depends(autenticado)):
    try:
        await gestor().cancelar_login(c.login_id)
    except ErroCodex as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True}


@r.post("/logout")
async def logout(s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    try:
        await gestor().terminar_sessao()
    except ErroCodex as exc:
        raise HTTPException(503, str(exc)) from exc
    await auditar(s, u.user.username, "codex-logout")
    await s.commit()
    return {"ok": True}
