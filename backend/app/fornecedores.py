"""Registo de fornecedores disponíveis para conversas e tarefas de equipa."""

from __future__ import annotations

from collections.abc import AsyncIterator

from . import ollama
from .sistema import estado_ollama


async def estados() -> dict:
    from . import codex
    return {
        "ollama": await estado_ollama(),
        "codex": await codex.gestor().estado(),
        "claude": {"ok": None, "externo": True, "nota": "Aplicação oficial separada."},
    }


async def modelos() -> list[dict]:
    from . import codex
    saida: list[dict] = []
    try:
        saida += await ollama.modelos()
    except Exception:  # noqa: BLE001
        pass
    saida += await codex.gestor().modelos()
    return saida


async def conversar(fornecedor: str, modelo: str, mensagens: list[dict], contexto: dict) -> AsyncIterator[dict]:
    """Eventos: {"tipo": "delta", "texto"}, {"tipo": "aprovacao", ...}, {"tipo": "aviso", "texto"}."""
    if fornecedor == "ollama":
        async for p in ollama.conversar(modelo, mensagens):
            yield {"tipo": "delta", "texto": p}
    elif fornecedor == "codex":
        from . import codex
        async for e in codex.gestor().conversar(modelo, mensagens, contexto):
            yield e
    elif fornecedor == "claude-code":
        from .claude_code import conversar as conversar_claude
        async for evento in conversar_claude(mensagens, contexto.get("tarefa_id")):
            yield evento
    else:
        raise ValueError(f"Fornecedor desconhecido: {fornecedor}")
