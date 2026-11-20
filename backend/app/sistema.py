"""Estado do servidor e dos fornecedores (para o painel). Created by Redfox using Claude"""

from __future__ import annotations

import httpx
import psutil

from .config import settings


def recursos() -> dict:
    disco = psutil.disk_usage(str(settings().data_dir)) if settings().data_dir.exists() else psutil.disk_usage("/")
    mem = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "ram": {"total": mem.total, "disponivel": mem.available, "percent": mem.percent},
        "disco": {"total": disco.total, "livre": disco.free, "percent": disco.percent},
    }


async def estado_ollama(cliente: httpx.AsyncClient | None = None) -> dict:
    proprio = cliente is None
    cliente = cliente or httpx.AsyncClient(timeout=3.0)
    try:
        v = (await cliente.get(f"{settings().ollama_url}/api/version")).json()
        return {"ok": True, "versao": v.get("version")}
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "erro": type(exc).__name__}
    finally:
        if proprio:
            await cliente.aclose()
