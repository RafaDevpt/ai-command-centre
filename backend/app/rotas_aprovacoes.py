"""
Aprovações: listar, ver, aprovar e rejeitar. Só o utilizador decide; a
decisão fica no registo de auditoria. Created by Redfox using Claude
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import aprovacoes
from .db import sessao
from .models import Approval, AuditLog
from .seguranca import Autenticado, agora, auditar, autenticado

r = APIRouter(prefix="/api", tags=["aprovacoes"])


class Decisao(BaseModel):
    decisao: str = Field(pattern="^(aprovar|rejeitar)$")


def _json(a: Approval) -> dict:
    return {"id": a.id, "origem": a.source, "tipo": a.kind, "resumo": a.summary, "detalhe": a.payload,
            "sessao_id": a.session_id, "estado": a.status, "resultado": a.result,
            "criada": a.created_at.isoformat() if a.created_at else None,
            "decidida": a.decided_at.isoformat() if a.decided_at else None, "decidida_por": a.decided_by}


@r.get("/approvals")
async def listar(estado: str | None = None, limite: int = 100, s: AsyncSession = Depends(sessao),
                 _: Autenticado = Depends(autenticado)):
    q = select(Approval).order_by(Approval.created_at.desc()).limit(min(max(limite, 1), 500))
    if estado:
        q = q.where(Approval.status == estado)
    pendentes = await s.scalar(select(func.count()).select_from(Approval).where(Approval.status == "pendente"))
    return {"pendentes": pendentes, "itens": [_json(a) for a in (await s.scalars(q)).all()]}


@r.get("/approvals/{ident}")
async def ver(ident: str, s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    a = await s.get(Approval, ident)
    if not a:
        raise HTTPException(404, "Aprovação não encontrada.")
    return _json(a)


@r.post("/approvals/{ident}")
async def decidir(ident: str, d: Decisao, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    a = await s.get(Approval, ident)
    if not a:
        raise HTTPException(404, "Aprovação não encontrada.")
    if a.status != "pendente":
        raise HTTPException(409, f"Esta aprovação já está «{a.status}».")
    aprovada = d.decisao == "aprovar"
    a.status = "aprovada" if aprovada else "rejeitada"
    a.decided_at, a.decided_by = agora(), u.user.username
    await auditar(s, u.user.username, "aprovacao-" + a.status, aprovacao=a.id, tipo=a.kind)
    await s.commit()
    aprovacoes.acordar(a.id, aprovada)
    return _json(a)


@r.get("/audit")
async def auditoria(limite: int = 200, s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(max(limite, 1), 1000))
    return [{"id": x.id, "quando": x.created_at.isoformat() if x.created_at else None, "quem": x.actor,
             "accao": x.action, "detalhe": x.detail} for x in (await s.scalars(q)).all()]


async def expirar_orfas(s: AsyncSession) -> int:
    """No arranque: pendentes de um processo anterior já não têm quem espere."""
    res = await s.execute(update(Approval).where(Approval.status == "pendente")
                          .values(status="expirada", decided_at=agora(), decided_by="sistema (reinício)"))
    await s.commit()
    return res.rowcount or 0
