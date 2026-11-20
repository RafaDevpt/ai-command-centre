"""
Codex app-server oficial (JSON-RPC 2.0 por stdio, sem o campo "jsonrpc").

- Um subprocesso por contentor, arrancado quando é preciso e parado ao fim
  de INACTIVO sem uso (poupa RAM).
- Login oficial «Sign in with ChatGPT» por código de dispositivo
  (account/login/start type=chatgptDeviceCode): servidor sem browser.
- Credenciais em CODEX_HOME (agents/codex, 700). Nunca saem daqui: a API só
  devolve se há sessão, o plano e o email mascarado.
- Threads em sandbox read-only, approvalPolicy=untrusted. Qualquer pedido de
  aprovação do Codex vira uma aprovação na página Aprovações; sem resposta,
  é recusado.

Created by Redfox using Claude
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path

from . import __version__, aprovacoes
from .config import settings

_log = logging.getLogger("aicc.codex")
INACTIVO = 15 * 60
TIMEOUT_PEDIDO = 60
ARGS = ["-c", 'cli_auth_credentials_store="file"', "-c", 'forced_login_method="chatgpt"']
NAO_SUPORTADO = {"item/tool/requestUserInput", "item/tool/call", "attestation/generate",
                 "account/chatgptAuthTokens/refresh"}


def _mascarar(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    nome, dominio = email.split("@", 1)
    return f"{nome[:1]}***@{dominio}"


class ErroCodex(RuntimeError):
    pass


class GestorCodex:
    def __init__(self, binario: Path | None = None, codex_home: Path | None = None,
                 socket: Path | None = None) -> None:
        self.binario = binario or Path(os.environ.get("AICC_CODEX_BIN", "/app/bin/codex-app-server"))
        self.home = codex_home or settings().data_dir / "agents" / "codex"
        #: Em produção o app-server corre noutro contentor (ver ponte_codex.py).
        self.socket = socket if socket is not None else (
            Path(os.environ["AICC_CODEX_SOCKET"]) if os.environ.get("AICC_CODEX_SOCKET") else None)
        self._proc: asyncio.subprocess.Process | None = None
        self._r: asyncio.StreamReader | None = None
        self._w: asyncio.StreamWriter | None = None
        self._leitor: asyncio.Task | None = None
        self._vigia: asyncio.Task | None = None
        self._pendentes: dict[int, asyncio.Future] = {}
        self._ouvintes: list[asyncio.Queue] = []
        self._proximo = 0
        self._ultimo_uso = time.monotonic()
        self._arranque = asyncio.Lock()
        self._em_uso = 0
        self._login: dict | None = None
        self._cache_estado: tuple[float, dict] | None = None
        self._cache_modelos: tuple[float, list] | None = None
        self._sessao_da_thread: dict[str, str] = {}
        self._aprovacao_do_item: dict[str, str] = {}

    @property
    def instalado(self) -> bool:
        if self.socket:
            return self.socket.is_socket()
        return self.binario.is_file() and os.access(self.binario, os.X_OK)

    def _vivo(self) -> bool:
        if self.socket:
            return self._w is not None and not self._w.is_closing()
        return self._proc is not None and self._proc.returncode is None

    # --- processo ---------------------------------------------------------
    async def _garantir(self) -> None:
        async with self._arranque:
            if self._vivo():
                return
            if not self.instalado:
                raise ErroCodex("O Codex app-server não está disponível (contentor «codex» parado?).")
            if self.socket:
                self._r, self._w = await asyncio.open_unix_connection(str(self.socket), limit=16 * 1024 * 1024)
            else:
                self.home.mkdir(parents=True, exist_ok=True)
                os.chmod(self.home, 0o700)
                (settings().data_dir / "logs").mkdir(parents=True, exist_ok=True)
                log = open(settings().data_dir / "logs" / "codex-app-server.log", "ab")  # noqa: SIM115
                env = {"CODEX_HOME": str(self.home), "HOME": "/tmp", "LANG": "C.UTF-8",
                       "PATH": f"{self.binario.parent}:/usr/bin:/bin"}
                self._proc = await asyncio.create_subprocess_exec(
                    str(self.binario), *ARGS, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=log, env=env, limit=16 * 1024 * 1024)
                self._r, self._w = self._proc.stdout, self._proc.stdin
            self._leitor = asyncio.create_task(self._ler())
            await self._pedido("initialize", {"clientInfo": {"name": "aicc", "title": "AI Command Centre",
                                                             "version": __version__}})
            await self._enviar({"method": "initialized"})
            if not self._vigia or self._vigia.done():
                self._vigia = asyncio.create_task(self._parar_se_inactivo())
            _log.info("Codex app-server iniciado.")

    async def _parar_se_inactivo(self) -> None:
        while self._vivo():
            await asyncio.sleep(60)
            if self._em_uso == 0 and self._login is None and time.monotonic() - self._ultimo_uso > INACTIVO:
                await self.parar()

    async def parar(self) -> None:
        if self._w and not self._w.is_closing():
            self._w.close()
        self._w = None
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), 10)
            except TimeoutError:
                self._proc.kill()
        self._proc = None

    async def _enviar(self, msg: dict) -> None:
        if not self._w:
            raise ErroCodex("Ligação ao Codex fechada.")
        self._w.write((json.dumps(msg) + "\n").encode())
        await self._w.drain()

    async def _pedido(self, metodo: str, params: dict | None = None, timeout: float = TIMEOUT_PEDIDO) -> dict:
        self._proximo += 1
        ident = self._proximo
        fut = asyncio.get_running_loop().create_future()
        self._pendentes[ident] = fut
        self._ultimo_uso = time.monotonic()
        await self._enviar({"method": metodo, "id": ident, **({"params": params} if params is not None else {})})
        try:
            resposta = await asyncio.wait_for(fut, timeout)
        finally:
            self._pendentes.pop(ident, None)
        if "error" in resposta:
            raise ErroCodex(str(resposta["error"].get("message", "erro do Codex"))[:300])
        return resposta.get("result") or {}

    async def _ler(self) -> None:
        assert self._r
        while True:
            try:
                linha = await self._r.readline()
            except (ConnectionError, ValueError):
                linha = b""
            if not linha:
                break
            try:
                msg = json.loads(linha)
            except ValueError:
                continue
            if "id" in msg and "method" not in msg:                     # resposta
                fut = self._pendentes.get(msg["id"])
                if fut and not fut.done():
                    fut.set_result(msg)
            elif "id" in msg and "method" in msg:                       # pedido do servidor
                asyncio.create_task(self._pedido_do_servidor(msg))
            elif "method" in msg:                                       # notificação
                self._notificacao(msg)
        self._w = None
        for fut in self._pendentes.values():
            if not fut.done():
                fut.set_result({"error": {"message": "O Codex app-server terminou."}})
        for q in list(self._ouvintes):
            q.put_nowait({"method": "_terminou"})

    def _notificacao(self, msg: dict) -> None:
        if msg["method"] == "account/login/completed":
            p = msg.get("params") or {}
            self._login = None
            self._cache_estado = None
            _log.info("Login do Codex terminado: %s", "ok" if p.get("success") else "falhou")
        elif msg["method"] == "account/updated":
            self._cache_estado = None
        for q in list(self._ouvintes):
            q.put_nowait(msg)

    # --- aprovações pedidas pelo Codex -------------------------------------
    async def _pedido_do_servidor(self, msg: dict) -> None:
        metodo, ident, p = msg["method"], msg["id"], msg.get("params") or {}
        try:
            if metodo in NAO_SUPORTADO:
                await self._enviar({"id": ident, "error": {"code": -32601, "message": "Não suportado pelo AI Command Centre."}})
                return
            if metodo == "mcpServer/elicitation/request":
                await self._enviar({"id": ident, "result": {"action": "decline", "content": None}})
                return
            tipo, resumo, detalhe = self._descrever(metodo, p)
            sessao_id = self._sessao_da_thread.get(p.get("threadId") or p.get("conversationId") or "")
            a = await aprovacoes.criar("codex", tipo, resumo, detalhe, sessao_id)
            for q in list(self._ouvintes):
                q.put_nowait({"method": "_aprovacao", "params": {"id": a.id, "resumo": resumo,
                                                                 "threadId": p.get("threadId")}})
            if p.get("itemId"):
                self._aprovacao_do_item[p["itemId"]] = a.id
            ok = await aprovacoes.esperar_decisao(a.id)
            await self._enviar({"id": ident, "result": self._resposta(metodo, p, ok)})
        except Exception:  # noqa: BLE001
            _log.exception("Pedido do servidor %s falhou; recuso.", metodo)
            await self._enviar({"id": ident, "result": self._resposta(metodo, p, False)})

    @staticmethod
    def _descrever(metodo: str, p: dict) -> tuple[str, str, dict]:
        if metodo in ("item/commandExecution/requestApproval", "execCommandApproval"):
            cmd = p.get("command")
            texto = " ".join(cmd) if isinstance(cmd, list) else str(cmd or "")
            return "comando", f"Executar: {texto[:200]}", {"comando": texto[:2000], "pasta": p.get("cwd"),
                                                          "motivo": p.get("reason")}
        if metodo in ("item/fileChange/requestApproval", "applyPatchApproval"):
            ficheiros = list((p.get("fileChanges") or p.get("changes") or {}).keys())[:20]
            return "ficheiro", f"Alterar ficheiros{': ' + ', '.join(ficheiros) if ficheiros else ''}"[:300], {
                "ficheiros": ficheiros, "raiz": p.get("grantRoot"), "motivo": p.get("reason")}
        if metodo == "item/permissions/requestApproval":
            return "permissoes", f"Pedir permissões adicionais: {str(p.get('reason') or '')[:150]}", {
                "permissoes": p.get("permissions"), "pasta": p.get("cwd"), "motivo": p.get("reason")}
        return "configuracao", f"Pedido do Codex: {metodo}", {"metodo": metodo}

    @staticmethod
    def _resposta(metodo: str, p: dict, ok: bool) -> dict:
        if metodo in ("execCommandApproval", "applyPatchApproval"):
            return {"decision": "approved" if ok else "denied"}
        if metodo == "item/permissions/requestApproval":
            return {"permissions": p.get("permissions") if ok else {}}
        return {"decision": "accept" if ok else "decline"}

    # --- interface de fornecedor ---------------------------------------------
    async def estado(self) -> dict:
        if not self.instalado:
            return {"ok": False, "instalado": False, "nota": "Codex não instalado."}
        if self._cache_estado and time.monotonic() - self._cache_estado[0] < 60:
            return self._cache_estado[1]
        try:
            await self._garantir()
            r = await self._pedido("account/read", {"refreshToken": False}, timeout=20)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "instalado": True, "nota": f"Erro: {type(exc).__name__}"}
        conta = r.get("account") or {}
        e = {"ok": bool(conta), "instalado": True, "plano": conta.get("planType"),
             "conta": _mascarar(conta.get("email")), "tipo": conta.get("type"),
             "nota": None if conta else "Sem sessão iniciada.", "login_pendente": bool(self._login)}
        self._cache_estado = (time.monotonic(), e)
        return e

    async def iniciar_login(self) -> dict:
        await self._garantir()
        r = await self._pedido("account/login/start", {"type": "chatgptDeviceCode"})
        self._login = {"loginId": r.get("loginId")}
        self._cache_estado = None
        return {"login_id": r.get("loginId"), "url": r.get("verificationUrl"), "codigo": r.get("userCode")}

    async def cancelar_login(self, login_id: str) -> None:
        await self._garantir()
        await self._pedido("account/login/cancel", {"loginId": login_id})
        self._login = None

    async def terminar_sessao(self) -> None:
        await self._garantir()
        await self._pedido("account/logout")
        self._cache_estado = None

    async def modelos(self) -> list[dict]:
        if not self.instalado:
            return []
        if self._cache_modelos and time.monotonic() - self._cache_modelos[0] < 3600:
            return self._cache_modelos[1]
        try:
            await self._garantir()
            r = await self._pedido("model/list", {"limit": 50, "includeHidden": False}, timeout=30)
        except Exception as exc:  # noqa: BLE001
            _log.warning("model/list falhou: %s", exc)
            return []
        saida = [{"id": m["id"], "fornecedor": "codex", "nome": m.get("displayName") or m["id"], "conversa": True,
                  "descricao": m.get("description"), "omissao": m.get("isDefault", False)}
                 for m in r.get("data", []) if not m.get("hidden")]
        self._cache_modelos = (time.monotonic(), saida)
        return saida

    async def conversar(self, modelo: str, mensagens: list[dict], contexto: dict) -> AsyncIterator[dict]:
        estado = await self.estado()
        if not estado.get("ok"):
            raise ErroCodex("Sem sessão no Codex. Inicie sessão em Definições → Codex.")
        sessao_conversa, bd = contexto["sessao"], contexto["bd"]
        instrucoes = next((m["content"] for m in mensagens if m["role"] == "system"), "")
        pasta = settings().data_dir / "projects" / (sessao_conversa.project_id or "_geral")
        pasta.mkdir(parents=True, exist_ok=True)
        fila: asyncio.Queue = asyncio.Queue()
        self._ouvintes.append(fila)
        self._em_uso += 1
        thread_id = sessao_conversa.external_id
        turno = None
        try:
            base = {"model": modelo, "cwd": str(pasta), "sandbox": "read-only", "approvalPolicy": "untrusted",
                    "developerInstructions": instrucoes}
            if thread_id:
                try:
                    await self._pedido("thread/resume", {"threadId": thread_id, **base})
                except ErroCodex:
                    thread_id = None
                    yield {"tipo": "aviso", "texto": "A thread anterior do Codex já não existe; comecei uma nova."}
            if not thread_id:
                r = await self._pedido("thread/start", {**base, "serviceName": "aicc"})
                thread_id = r["thread"]["id"]
                sessao_conversa.external_id = thread_id
                await bd.commit()
            self._sessao_da_thread[thread_id] = sessao_conversa.id
            ultima = next(m["content"] for m in reversed(mensagens) if m["role"] == "user")
            r = await self._pedido("turn/start", {"threadId": thread_id,
                                                   "input": [{"type": "text", "text": ultima}]})
            turno = (r.get("turn") or {}).get("id")
            while True:
                msg = await fila.get()
                m, p = msg["method"], msg.get("params") or {}
                if m == "_terminou":
                    raise ErroCodex("O Codex app-server terminou a meio.")
                if p.get("threadId") not in (None, thread_id):
                    continue
                if m == "item/agentMessage/delta":
                    yield {"tipo": "delta", "texto": p.get("delta", "")}
                elif m == "_aprovacao":
                    yield {"tipo": "aprovacao", "id": p["id"], "resumo": p["resumo"]}
                elif m == "item/completed":
                    item = p.get("item") or {}
                    a_id = self._aprovacao_do_item.pop(item.get("id", ""), None)
                    if a_id:
                        codigo = item.get("exitCode")
                        saida = str(item.get("aggregatedOutput") or item.get("status") or "")
                        await aprovacoes.registar_resultado(a_id, codigo in (0, None), f"código {codigo}\n{saida}")
                elif m == "turn/completed":
                    t = p.get("turn") or {}
                    if t.get("status") == "failed":
                        raise ErroCodex(((t.get("error") or {}).get("message") or "O turno falhou.")[:300])
                    turno = None
                    break
        finally:
            if turno and thread_id and self._vivo():
                try:
                    await self._pedido("turn/interrupt", {"threadId": thread_id, "turnId": turno}, timeout=10)
                except Exception:  # noqa: BLE001
                    pass
            self._ouvintes.remove(fila)
            self._em_uso -= 1
            self._ultimo_uso = time.monotonic()


_gestor: GestorCodex | None = None


def gestor() -> GestorCodex:
    global _gestor
    if _gestor is None:
        _gestor = GestorCodex()
    return _gestor
