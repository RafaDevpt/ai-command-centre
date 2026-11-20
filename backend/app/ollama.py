"""
Cliente do Ollama já instalado (só 127.0.0.1). Só lê modelos existentes:
nunca chama /api/pull nem /api/delete.

Created by Redfox using Claude
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from .config import settings

NUM_CTX = 4096          # contexto modesto: CPU sem GPU e 16 GB partilhados
KEEP_ALIVE = "2m"       # liberta a RAM pouco depois da última resposta


def _url(caminho: str) -> str:
    return settings().ollama_url.rstrip("/") + caminho


async def modelos() -> list[dict]:
    async with httpx.AsyncClient(timeout=5) as c:
        tags = (await c.get(_url("/api/tags"))).json().get("models", [])
        try:
            carregados = {m["name"] for m in (await c.get(_url("/api/ps"))).json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            carregados = set()
    saida = []
    for m in tags:
        d = m.get("details") or {}
        saida.append({
            "id": m["name"], "fornecedor": "ollama", "nome": m["name"], "tamanho": m.get("size"),
            "familia": d.get("family"), "parametros": d.get("parameter_size"),
            "quantizacao": d.get("quantization_level"), "carregado": m["name"] in carregados,
            "conversa": "embed" not in m["name"],
        })
    return saida


async def detalhes(nome: str) -> dict:
    """Contexto máximo e outros dados de um modelo (pedido leve ao /api/show)."""
    async with httpx.AsyncClient(timeout=10) as c:
        d = (await c.post(_url("/api/show"), json={"model": nome})).json()
    info = d.get("model_info") or {}
    contexto = next((v for k, v in info.items() if k.endswith(".context_length")), None)
    return {"id": nome, "contexto_max": contexto, "contexto_usado": NUM_CTX,
            "familia": (d.get("details") or {}).get("family"), "capacidades": d.get("capabilities", [])}


async def conversar(modelo: str, mensagens: list[dict]) -> AsyncIterator[str]:
    """Respostas em streaming (pedaços de texto)."""
    corpo = {"model": modelo, "messages": mensagens, "stream": True, "think": False,
             "keep_alive": KEEP_ALIVE, "options": {"num_ctx": NUM_CTX}}
    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=5)) as c:
        async with c.stream("POST", _url("/api/chat"), json=corpo) as r:
            if r.status_code != 200:
                texto = (await r.aread()).decode(errors="replace")[:200]
                raise RuntimeError(f"Ollama respondeu {r.status_code}: {texto}")
            async for linha in r.aiter_lines():
                if not linha.strip():
                    continue
                d = json.loads(linha)
                if d.get("error"):
                    raise RuntimeError(d["error"])
                pedaco = (d.get("message") or {}).get("content", "")
                if pedaco:
                    yield pedaco
                if d.get("done"):
                    break


async def gerar(modelo: str, mensagens: list[dict]) -> str:
    return "".join([p async for p in conversar(modelo, mensagens)])


async def embedding(texto: str, modelo: str = "nomic-embed-text:latest") -> list[float]:
    async with httpx.AsyncClient(timeout=60) as c:
        d = (await c.post(_url("/api/embed"), json={"model": modelo, "input": texto[:8000],
                                                     "keep_alive": KEEP_ALIVE})).json()
    return (d.get("embeddings") or [[]])[0]
