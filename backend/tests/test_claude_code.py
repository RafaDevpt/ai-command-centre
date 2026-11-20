"""Execução do CLI sem API e sem expor prompt nos argumentos do processo."""

import asyncio
import json

import pytest

from app import claude_code


def test_stream_json_cli_e_prompt_por_stdin(tmp_path, monkeypatch):
    argv_file = tmp_path / "args.json"
    cli = tmp_path / "claude-falso"
    cli.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "if sys.argv[1:] == ['auth', 'status']:\n"
        " print(json.dumps({'loggedIn':True,'apiProvider':'firstParty','authMethod':'claude.ai'})); raise SystemExit(0)\n"
        f"pathlib.Path({str(argv_file)!r}).write_text(json.dumps(sys.argv[1:]))\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'type':'stream_event','event':{'type':'content_block_delta','delta':{'type':'text_delta','text':'olá'}}}))\n"
        "print(json.dumps({'type':'result','result':'olá'}))\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: str(cli))
    eventos = asyncio.run(_eventos([{"role": "user", "content": "prompt privada"}]))
    args = json.loads(argv_file.read_text(encoding="utf-8"))
    assert [e["texto"] for e in eventos] == ["olá"]
    assert "prompt privada" not in args
    assert "--output-format" in args and "stream-json" in args
    assert "--verbose" in args
    assert "--tools" in args and args[args.index("--tools") + 1] == ""
    assert "--no-session-persistence" in args


def test_chaves_de_api_sao_removidas_do_ambiente(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "valor-nao-utilizado")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "nao-utilizar")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy-invalido")
    ambiente = claude_code._ambiente()
    assert "ANTHROPIC_API_KEY" not in ambiente
    assert "CLAUDE_CODE_USE_BEDROCK" not in ambiente
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in ambiente and "HTTPS_PROXY" not in ambiente


def test_cliente_socket_stream_and_erros(tmp_path, monkeypatch):
    import asyncio

    async def executar():
        socket = tmp_path / "claude.sock"
        prompts = []

        async def responder(reader, writer):
            pedido = json.loads(await reader.readline())
            prompts.append(pedido["prompt"])
            writer.write(b'{"type":"delta","text":"parte 1"}\n')
            writer.write(b'{"type":"delta","text":"parte 2"}\n')
            writer.write(b'{"type":"done"}\n')
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        servidor = await asyncio.start_unix_server(responder, path=str(socket))
        monkeypatch.setenv("AICC_CLAUDE_SOCKET", str(socket))
        try:
            saida = [e async for e in claude_code.conversar([{"role": "user", "content": "pedido"}], "t1")]
        finally:
            servidor.close()
            await servidor.wait_closed()
        return saida, prompts

    saida, prompts = asyncio.run(executar())
    assert [e["texto"] for e in saida] == ["parte 1", "parte 2"]
    assert "pedido" in prompts[0]


async def _eventos(mensagens):
    return [e async for e in claude_code.conversar(mensagens, "teste")]


def test_cli_nao_encontrado_falha_sem_prompt(monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="não encontrado"):
        asyncio.run(_eventos([{"role": "user", "content": "confidencial"}]))
