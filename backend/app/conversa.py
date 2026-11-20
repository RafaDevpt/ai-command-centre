"""
Núcleo da conversa, partilhado pelo WebSocket e pelos testes: guarda a
mensagem do utilizador, monta o histórico (com contexto do projecto e
anexos), pede a resposta ao fornecedor em streaming e guarda-a com o
fornecedor e o modelo que a geraram.

Created by Redfox using Claude
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import fornecedores
from .anexos import ler_texto
from .contexto import contexto_projecto
from .models import ChatSession, Message
from .seguranca import agora

HISTORICO = 20          # últimas mensagens enviadas ao modelo
SISTEMA = ("És um assistente no AI Command Centre pessoal do utilizador. Responde em português europeu, "
           "salvo pedido em contrário. Sê claro e conciso.")


async def historico(s: AsyncSession, sessao: ChatSession) -> list[dict]:
    msgs = (await s.scalars(select(Message).where(Message.session_id == sessao.id)
                            .order_by(Message.id.desc()).limit(HISTORICO))).all()
    saida = []
    for m in reversed(msgs):
        texto = m.content
        for a in m.attachments or []:
            if a.get("texto"):
                texto += f"\n\n[Anexo «{a.get('nome')}»]\n" + ler_texto(a["id"])
        saida.append({"role": m.role, "content": texto})
    return saida


async def responder(s: AsyncSession, sessao: ChatSession, texto: str, anexos: list[dict]) -> AsyncIterator[dict]:
    s.add(Message(session_id=sessao.id, role="user", content=texto, attachments=anexos))
    if sessao.title == "Nova conversa":
        sessao.title = (texto.strip().splitlines() or ["Nova conversa"])[0][:60] or "Nova conversa"
    sessao.last_activity = agora()
    await s.commit()

    sistema = SISTEMA
    ctx = await contexto_projecto(s, sessao.project_id)
    if ctx:
        sistema += "\n\n" + ctx
    mensagens = [{"role": "system", "content": sistema}] + await historico(s, sessao)

    partes: list[str] = []
    erro = None
    try:
        async for e in fornecedores.conversar(sessao.provider, sessao.model, mensagens,
                                              {"sessao": sessao, "bd": s}):
            if e["tipo"] == "delta":
                partes.append(e["texto"])
            yield e
    except Exception as exc:  # noqa: BLE001
        erro = f"{type(exc).__name__}: {str(exc)[:200]}"
    resposta = "".join(partes)
    if resposta or erro:
        m = Message(session_id=sessao.id, role="assistant", provider=sessao.provider, model=sessao.model,
                    content=resposta or f"⚠️ {erro}")
        s.add(m)
        sessao.last_activity = agora()
        await s.commit()
        yield {"tipo": "fim", "mensagem_id": m.id, "erro": erro, "fornecedor": sessao.provider,
               "modelo": sessao.model}
