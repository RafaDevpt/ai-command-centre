"""
Aplicação FastAPI: API em /api e o frontend (build do Vite) servido como
ficheiros estáticos, com fallback para index.html (SPA).

Created by Redfox using Claude
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from . import __version__
from .config import settings
from .db import sessao
from .sistema import estado_ollama, recursos



@asynccontextmanager
async def ciclo(_app: FastAPI):
    # Recuperação após reinício: o que ficou pendente já não tem quem espere.
    try:
        async for s in sessao():
            await rotas_aprovacoes.expirar_orfas(s)
            await agentes.recuperar(s)
            await agentes.semear(s)
    except Exception:  # noqa: BLE001
        logging.getLogger("aicc").exception("Não consegui limpar aprovações órfãs.")
    yield
    await codex.gestor().parar()


app = FastAPI(title="AI Command Centre", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=ciclo)

from . import (agentes, codex, rotas_agentes, rotas_aprovacoes, rotas_auth, rotas_codex,  # noqa: E402
               rotas_claude, rotas_conversa, rotas_painel, rotas_projectos)

for _rota in (rotas_auth.r, rotas_painel.r, rotas_conversa.r, rotas_codex.r, rotas_aprovacoes.r,
              rotas_projectos.r, rotas_agentes.r, rotas_claude.r):
    app.include_router(_rota)


@app.middleware("http")
async def cabecalhos_seguranca(pedido, seguinte):
    r = await seguinte(pedido)
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("X-Frame-Options", "DENY")
    r.headers.setdefault("Referrer-Policy", "no-referrer")
    r.headers.setdefault("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
    return r


@app.get("/api/health")
async def vivo() -> dict:
    """Liveness: o processo responde. Não toca na BD."""
    return {"status": "ok", "versao": __version__}


@app.get("/api/health/ready")
async def pronto(s: AsyncSession = Depends(sessao)) -> JSONResponse:
    """Readiness: BD e Ollama. 503 se a BD falhar (o Ollama é opcional)."""
    try:
        await s.execute(text("SELECT 1"))
        bd = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        bd = {"ok": False, "erro": type(exc).__name__}
    ollama = await estado_ollama()
    estado = 200 if bd["ok"] else 503
    return JSONResponse({"bd": bd, "ollama": ollama, "recursos": recursos()}, status_code=estado)


@app.get("/{caminho:path}", include_in_schema=False)
async def spa(caminho: str):
    if caminho.startswith("api/"):
        return JSONResponse({"detail": "Não encontrado."}, status_code=404)
    raiz: Path = settings().static_dir
    pedido = (raiz / caminho).resolve()
    if caminho and pedido.is_file() and raiz.resolve() in pedido.parents:
        return FileResponse(pedido)
    indice = raiz / "index.html"
    if indice.is_file():
        return FileResponse(indice)
    return JSONResponse({"detail": "frontend ainda não construído"}, status_code=404)
