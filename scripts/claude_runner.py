#!/usr/bin/env python3
"""Runner anfitrião do CLI Claude Code; socket privado para o backend aicc."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

SEM_AMBIENTE = {
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS",
    "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_API_KEY", "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
}
MAX_PROMPT = 500_000


def ambiente_seguro() -> dict[str, str]:
    env = os.environ.copy()
    for chave in SEM_AMBIENTE:
        env.pop(chave, None)
    return env


async def enviar(writer: asyncio.StreamWriter, evento: dict) -> None:
    writer.write((json.dumps(evento, ensure_ascii=False) + "\n").encode())
    await writer.drain()


async def validar_sessao(cli: str, env: dict[str, str]) -> bool:
    proc = await asyncio.create_subprocess_exec(cli, "auth", "status", stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL, env=env)
    try:
        saida, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        estado = json.loads(saida)
    except (TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        return False
    return (proc.returncode == 0 and estado.get("loggedIn") is True
            and estado.get("authMethod") == "claude.ai" and estado.get("apiProvider") == "firstParty")


async def executar(prompt: str, cli: str, writer: asyncio.StreamWriter) -> None:
    env = ambiente_seguro()
    if not await validar_sessao(cli, env):
        await enviar(writer, {"type": "error", "message": "Claude Code sem sessão first-party autenticada."})
        return
    # Isolamento: sem ferramentas, sem servidores MCP (nem os globais do utilizador), sem definições,
    # plugins nem hooks do utilizador, sem comandos «/», numa pasta vazia que é apagada no fim.
    # Isolation: no tools, no MCP servers (not even the user's global ones), no user settings,
    # plugins or hooks, no slash commands, in an empty folder removed afterwards.
    pasta = tempfile.mkdtemp(prefix="aicc-claude-")
    try:
        proc = await asyncio.create_subprocess_exec(
            cli, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
            "--no-session-persistence", "--tools", "", "--permission-mode", "plan",
            "--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env=env, cwd=pasta,
        )
        await _conversar(proc, prompt, writer)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


async def _conversar(proc: asyncio.subprocess.Process, prompt: str, writer: asyncio.StreamWriter) -> None:
    assert proc.stdin and proc.stdout
    proc.stdin.write(prompt.encode())
    await proc.stdin.drain()
    proc.stdin.close()
    teve_texto = False
    try:
        while linha := await asyncio.wait_for(proc.stdout.readline(), timeout=1800):
            try:
                evento = json.loads(linha)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if evento.get("type") == "stream_event":
                parte = evento.get("event") or {}
                delta = parte.get("delta") or {}
                if parte.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                    texto = delta.get("text") or ""
                    if texto:
                        teve_texto = True
                        await enviar(writer, {"type": "delta", "text": texto})
            elif evento.get("type") == "result" and not teve_texto and evento.get("result"):
                teve_texto = True
                await enviar(writer, {"type": "delta", "text": evento["result"]})
        codigo = await asyncio.wait_for(proc.wait(), timeout=30)
        if codigo:
            await enviar(writer, {"type": "error", "message": f"Claude Code terminou com código {codigo}."})
        elif not teve_texto:
            await enviar(writer, {"type": "error", "message": "Claude Code terminou sem produzir uma resposta."})
        else:
            await enviar(writer, {"type": "done"})
    except (TimeoutError, asyncio.TimeoutError):
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        await enviar(writer, {"type": "error", "message": "Claude Code excedeu o tempo limite."})
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        raise
    except (ConnectionError, BrokenPipeError):
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except TimeoutError:
                proc.kill()
                await proc.wait()


async def ligação(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, cli: str) -> None:
    try:
        linha = await asyncio.wait_for(reader.readline(), timeout=30)
        if not linha or len(linha) > MAX_PROMPT:
            await enviar(writer, {"type": "error", "message": "Pedido vazio ou demasiado grande."})
            return
        try:
            pedido = json.loads(linha)
        except json.JSONDecodeError:
            await enviar(writer, {"type": "error", "message": "Pedido inválido."})
            return
        prompt = pedido.get("prompt") if isinstance(pedido, dict) else None
        if not isinstance(prompt, str) or not prompt.strip():
            await enviar(writer, {"type": "error", "message": "Pedido sem prompt."})
            return

        trabalhador = asyncio.create_task(executar(prompt, cli, writer))
        desconexão = asyncio.create_task(reader.read(1))
        feito, pendente = await asyncio.wait({trabalhador, desconexão}, return_when=asyncio.FIRST_COMPLETED)
        if desconexão in feito:
            trabalhador.cancel()
            await asyncio.gather(trabalhador, return_exceptions=True)
        else:
            desconexão.cancel()
            await asyncio.gather(desconexão, return_exceptions=True)
            await trabalhador
    except (TimeoutError, asyncio.TimeoutError):
        try:
            await enviar(writer, {"type": "error", "message": "Tempo limite ao receber o pedido."})
        except ConnectionError:
            pass
    except (ConnectionError, BrokenPipeError):
        pass
    except Exception:  # erros internos não incluem prompts nem detalhes do ambiente
        try:
            await enviar(writer, {"type": "error", "message": "Erro interno no runner Claude Code."})
        except ConnectionError:
            pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass


async def servidor(socket: Path, cli: str) -> None:
    socket.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(socket.parent, 0o700)
    if socket.exists():
        if not socket.is_socket():
            raise RuntimeError("O caminho reservado ao socket Claude já existe e não é um socket.")
        socket.unlink()
    server = await asyncio.start_unix_server(lambda r, w: ligação(r, w, cli), path=str(socket), limit=MAX_PROMPT + 1024)
    os.chmod(socket, 0o600)
    async with server:
        await server.serve_forever()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--socket", type=Path, required=True)
    p.add_argument("--cli", default=shutil.which("claude") or "claude")
    args = p.parse_args()
    try:
        asyncio.run(servidor(args.socket, args.cli))
    except KeyboardInterrupt:
        pass
    finally:
        if args.socket.is_socket():
            args.socket.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
