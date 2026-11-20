"""Painel: estado dos fornecedores, actividade recente e recursos. Created by Redfox using Claude"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import sessao
from .models import Approval, ChatSession, CollabTask
from .seguranca import Autenticado, autenticado
from .sistema import estado_ollama, recursos

r = APIRouter(prefix="/api", tags=["painel"])


@r.get("/dashboard")
async def painel(a: Autenticado = Depends(autenticado), s: AsyncSession = Depends(sessao)):
    from . import fornecedores   # import tardio: evita ciclos
    recentes = (await s.scalars(select(ChatSession).order_by(ChatSession.last_activity.desc()).limit(6))).all()
    pendentes = await s.scalar(select(func.count()).select_from(Approval).where(Approval.status == "pendente"))
    a_correr = await s.scalar(select(func.count()).select_from(CollabTask)
                              .where(CollabTask.status.in_(["pendente", "a-correr"])))
    return {
        "fornecedores": await fornecedores.estados(),
        "ollama": await estado_ollama(),
        "sessoes_recentes": [{"id": c.id, "titulo": c.title, "fornecedor": c.provider, "modelo": c.model,
                              "ultima": c.last_activity, "estado": c.status} for c in recentes],
        "aprovacoes_pendentes": pendentes or 0,
        "tarefas_a_correr": a_correr or 0,
        "recursos": recursos(),
    }
