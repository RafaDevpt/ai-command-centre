"""Integração local com o CLI oficial Claude Code, usando a sessão já autenticada.

Não lê nem copia credenciais. O CLI recebe a prompt por stdin, não tem ferramentas
activadas e emite eventos stream-json para acompanhar a resposta em tempo real.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import AsyncIterator

_processos: dict[str, asyncio.subprocess.Process] = {}
_ligações: dict[str, asyncio.StreamWriter] = {}
_TIMEOUT = 1800
_CHAVES_NAO_PERMITIDAS = {
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS",
    "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_API_KEY",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
}


def _ambiente() -> dict[str, str]:
    """Mantém o ambiente do CLI, removendo credenciais e fornecedores de API."""
    ambiente = os.environ.copy()
    for chave in _CHAVES_NAO_PERMITIDAS:
        ambiente.pop(chave, None)
    return ambiente


async def _validar_sessao(binario: str, ambiente: dict[str, str]) -> None:
    """Só permite a sessão oficial first-party; nunca devolve nem regista o JSON."""
    proc = await asyncio.create_subprocess_exec(
        binario, "auth", "status", stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, env=ambiente,
    )
    try:
        saida, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Não foi possível verificar a sessão local do Claude Code.") from exc
    try:
        estado = json.loads(saida)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("O estado de autenticação do Claude Code não está disponível.") from exc
    if (proc.returncode or not estado.get("loggedIn") or estado.get("apiProvider") != "firstParty"
            or estado.get("authMethod") != "claude.ai"):
        raise RuntimeError("Claude Code não tem uma sessão first-party autenticada neste runtime.")


def _prompt(mensagens: list[dict]) -> str:
    return "\n\n".join(f"{m['role'].upper()}:\n{m['content']}" for m in mensagens)


async def conversar(mensagens: list[dict], tarefa_id: str | None = None) -> AsyncIterator[dict]:
    """Executa uma prompt sem ferramentas e transmite deltas de texto do Claude."""
    socket = os.environ.get("AICC_CLAUDE_SOCKET")
    if socket:
        async for evento in _conversar_socket(_prompt(mensagens), socket, tarefa_id):
            yield evento
        return
    binario = shutil.which("claude")
    if not binario:
        raise RuntimeError("Claude Code CLI não encontrado no PATH do servidor.")
    ambiente = _ambiente()
    await _validar_sessao(binario, ambiente)
    # Mesmo isolamento do runner: sem MCP, definições, plugins nem hooks do utilizador; pasta vazia.
    pasta = tempfile.mkdtemp(prefix="aicc-claude-")
    proc = await asyncio.create_subprocess_exec(
        binario, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
        "--no-session-persistence", "--tools", "", "--permission-mode", "plan",
        "--strict-mcp-config", "--setting-sources", "", "--disable-slash-commands",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, env=ambiente, cwd=pasta,
    )
    if tarefa_id:
        _processos[tarefa_id] = proc
    prompt = _prompt(mensagens).encode("utf-8")
    assert proc.stdin is not None
    proc.stdin.write(prompt)
    await proc.stdin.drain()
    proc.stdin.close()
    partes: list[str] = []
    try:
        assert proc.stdout is not None
        while True:
            linha = await asyncio.wait_for(proc.stdout.readline(), timeout=_TIMEOUT)
            if not linha:
                break
            try:
                evento = json.loads(linha)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if evento.get("type") == "stream_event":
                e = evento.get("event") or {}
                if e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta":
                    texto = e["delta"].get("text", "")
                    if texto:
                        partes.append(texto)
                        yield {"tipo": "delta", "texto": texto}
            elif evento.get("type") == "result" and not partes:
                texto = evento.get("result") or ""
                if texto:
                    partes.append(texto)
                    yield {"tipo": "delta", "texto": texto}
        codigo = await asyncio.wait_for(proc.wait(), timeout=30)
        if codigo:
            raise RuntimeError(f"Claude Code terminou com código {codigo}.")
        if not partes:
            raise RuntimeError("Claude Code terminou sem produzir uma resposta.")
    except (TimeoutError, asyncio.TimeoutError) as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError("Claude Code excedeu o tempo limite de execução.") from exc
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        raise
    finally:
        if tarefa_id and _processos.get(tarefa_id) is proc:
            _processos.pop(tarefa_id, None)
        shutil.rmtree(pasta, ignore_errors=True)


async def interromper(tarefa_id: str) -> None:
    writer = _ligações.get(tarefa_id)
    if writer and not writer.is_closing():
        writer.close()
    proc = _processos.get(tarefa_id)
    if proc and proc.returncode is None:
        proc.terminate()


async def _conversar_socket(prompt: str, socket: str, tarefa_id: str | None) -> AsyncIterator[dict]:
    leitor, escritor = await asyncio.open_unix_connection(socket, limit=2 * 1024 * 1024)
    if tarefa_id:
        _ligações[tarefa_id] = escritor
    escritor.write((json.dumps({"prompt": prompt}, ensure_ascii=False) + "\n").encode())
    await escritor.drain()
    try:
        while linha := await leitor.readline():
            evento = json.loads(linha)
            if evento.get("type") == "delta":
                yield {"tipo": "delta", "texto": evento.get("text", "")}
            elif evento.get("type") == "error":
                raise RuntimeError(str(evento.get("message") or "Erro no runner Claude."))
            elif evento.get("type") == "done":
                return
        raise RuntimeError("Ligação ao runner Claude interrompida antes da conclusão.")
    finally:
        if tarefa_id and _ligações.get(tarefa_id) is escritor:
            _ligações.pop(tarefa_id, None)
        escritor.close()
        try:
            await escritor.wait_closed()
        except (ConnectionError, OSError):
            pass

