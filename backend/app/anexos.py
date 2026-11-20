"""
Anexos de conversa: guardados em attachments/AAAA-MM/, até 5 MB. O texto de
ficheiros de texto é extraído e vai para o contexto (truncado).

Created by Redfox using Claude
"""

from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import settings

MAX_BYTES = 5 * 1024 * 1024
TEXTO = {".txt", ".md", ".py", ".js", ".ts", ".tsx", ".json", ".yaml", ".yml", ".csv", ".log", ".sql", ".html",
         ".css", ".sh", ".toml", ".ini", ".xml"}
_ID = re.compile(r"^[0-9]{4}-[0-9]{2}/[a-f0-9]{16}_[A-Za-z0-9._-]{1,120}$")


def pasta() -> Path:
    return settings().data_dir / "attachments"


def nome_seguro(nome: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(nome or "ficheiro").name).strip("._") or "ficheiro"
    return base[:120]


async def guardar(ficheiro: UploadFile, destino: Path | None = None) -> dict:
    conteudo = await ficheiro.read(MAX_BYTES + 1)
    if len(conteudo) > MAX_BYTES:
        raise HTTPException(413, "Ficheiro maior que 5 MB.")
    mes = datetime.now(UTC).strftime("%Y-%m")
    ident = f"{mes}/{secrets.token_hex(8)}_{nome_seguro(ficheiro.filename or '')}"
    caminho = (destino or pasta()) / ident
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    caminho.chmod(0o600)
    return {"id": ident, "nome": ficheiro.filename or "ficheiro", "tamanho": len(conteudo),
            "texto": caminho.suffix.lower() in TEXTO}


def ler_texto(ident: str, limite: int = 12000) -> str:
    if not _ID.match(ident):
        raise HTTPException(400, "Anexo inválido.")
    caminho = (pasta() / ident).resolve()
    if pasta().resolve() not in caminho.parents or not caminho.is_file():
        raise HTTPException(404, "Anexo não encontrado.")
    if caminho.suffix.lower() not in TEXTO:
        return ""
    return caminho.read_bytes()[:limite].decode("utf-8", errors="replace")
