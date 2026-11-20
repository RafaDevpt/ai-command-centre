"""
Ponte do contentor «codex»: escuta num socket Unix (pasta partilhada só com
a aplicação) e, por cada ligação, arranca o Codex app-server oficial e liga
stdin/stdout ao socket. Uma ligação de cada vez; ao fechar, o processo morre.

Este contentor não vê a base de dados, os segredos nem os anexos: só
agents/codex (credenciais do Codex) e projects (só leitura).

Created by Redfox using Claude
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

SOCKET = Path(os.environ.get("AICC_CODEX_SOCKET", "/run/aicc-codex/codex.sock"))
BIN = os.environ.get("AICC_CODEX_BIN", "/app/bin/codex-app-server")
LOG = Path(os.environ.get("AICC_CODEX_LOG", "/data/ai-command-centre/logs/codex-app-server.log"))
_log = logging.getLogger("aicc.ponte")
_ocupado = asyncio.Lock()


async def _copiar(de: asyncio.StreamReader, para: asyncio.StreamWriter) -> None:
    try:
        while bloco := await de.read(65536):
            para.write(bloco)
            await para.drain()
    except (ConnectionError, BrokenPipeError):
        pass
    finally:
        try:
            para.close()
        except Exception:  # noqa: BLE001
            pass


async def _ligacao(leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
    if _ocupado.locked():
        escritor.close()
        return
    async with _ocupado:
        args = sys.argv[1:]
        with open(LOG, "ab") as log:
            proc = await asyncio.create_subprocess_exec(BIN, *args, stdin=asyncio.subprocess.PIPE,
                                                        stdout=asyncio.subprocess.PIPE, stderr=log)
            _log.info("Codex app-server iniciado (pid %s).", proc.pid)
            assert proc.stdin and proc.stdout
            await asyncio.wait([asyncio.create_task(_copiar(leitor, proc.stdin)),
                                asyncio.create_task(_copiar(proc.stdout, escritor))],
                               return_when=asyncio.FIRST_COMPLETED)
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), 10)
                except TimeoutError:
                    proc.kill()
            escritor.close()
            _log.info("Codex app-server terminado.")


async def principal() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Path(os.environ["CODEX_HOME"]).mkdir(parents=True, exist_ok=True)
    os.chmod(os.environ["CODEX_HOME"], 0o700)
    SOCKET.unlink(missing_ok=True)
    os.umask(0o077)
    servidor = await asyncio.start_unix_server(_ligacao, path=str(SOCKET), limit=16 * 1024 * 1024)
    _log.info("Ponte do Codex à escuta em %s", SOCKET)
    async with servidor:
        await servidor.serve_forever()


if __name__ == "__main__":
    asyncio.run(principal())
