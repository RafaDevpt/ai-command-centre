"""
Registo de aprovações em memória (futuros à espera da decisão) + regras
comuns. A decisão é sempre gravada na BD primeiro; só depois se acorda quem
espera. Um pedido sem decisão em PRAZO expira como recusado.

Created by Redfox using Claude
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from .db import motor, sessao
from .models import Approval
from .seguranca import agora, auditar

PRAZO = timedelta(minutes=15)
_espera: dict[str, asyncio.Future] = {}


async def criar(source: str, kind: str, summary: str, payload: dict, session_id: str | None) -> Approval:
    motor()
    async for s in sessao():
        a = Approval(source=source, kind=kind, summary=summary[:300], payload=payload, session_id=session_id)
        s.add(a)
        await auditar(s, source, "aprovacao-pedida", aprovacao=a.id, tipo=kind)
        await s.commit()
        return a
    raise RuntimeError("sem BD")


async def esperar_decisao(aprovacao_id: str) -> bool:
    """True se aprovada. Expira (recusa) ao fim de PRAZO."""
    fut = _espera.setdefault(aprovacao_id, asyncio.get_running_loop().create_future())
    try:
        return await asyncio.wait_for(asyncio.shield(fut), PRAZO.total_seconds())
    except TimeoutError:
        async for s in sessao():
            a = await s.get(Approval, aprovacao_id)
            if a and a.status == "pendente":
                a.status, a.decided_at, a.decided_by = "expirada", agora(), "sistema"
                await s.commit()
        return False
    finally:
        _espera.pop(aprovacao_id, None)


def acordar(aprovacao_id: str, aprovada: bool) -> None:
    fut = _espera.get(aprovacao_id)
    if fut and not fut.done():
        fut.get_loop().call_soon_threadsafe(lambda: fut.done() or fut.set_result(aprovada))


async def registar_resultado(aprovacao_id: str, sucesso: bool, resultado: str) -> None:
    async for s in sessao():
        a = await s.get(Approval, aprovacao_id)
        if a and a.status == "aprovada":
            a.status = "executada" if sucesso else "falhou"
            a.result = resultado[:4000]
            await s.commit()
