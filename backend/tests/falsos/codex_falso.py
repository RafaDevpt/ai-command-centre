"""Codex app-server falso para os testes (mesmo protocolo, sem rede). Created by Redfox using Claude"""
import json
import os
import sys
from pathlib import Path

HOME = Path(os.environ["CODEX_HOME"])
SESSAO = HOME / "sessao-falsa"
threads: set[str] = set()


def enviar(m):
    sys.stdout.write(json.dumps(m) + "\n")
    sys.stdout.flush()


def ler():
    linha = sys.stdin.readline()
    if not linha:
        sys.exit(0)
    return json.loads(linha)


while True:
    m = ler()
    met, ident, p = m.get("method"), m.get("id"), m.get("params") or {}
    if ident is None:
        continue
    if met == "initialize":
        enviar({"id": ident, "result": {"userAgent": "falso"}})
    elif met == "account/read":
        conta = {"type": "chatgpt", "email": "redfox@example.com", "planType": "go"} if SESSAO.exists() else None
        enviar({"id": ident, "result": {"account": conta, "requiresOpenaiAuth": True}})
    elif met == "account/login/start":
        assert p == {"type": "chatgptDeviceCode"}
        enviar({"id": ident, "result": {"type": "chatgptDeviceCode", "loginId": "L1", "userCode": "ABCD-1234",
                                        "verificationUrl": "https://auth.openai.com/codex/device"}})
        SESSAO.write_text("x")
        enviar({"method": "account/login/completed", "params": {"loginId": "L1", "success": True, "error": None}})
    elif met == "account/logout":
        SESSAO.unlink(missing_ok=True)
        enviar({"id": ident, "result": {}})
    elif met == "model/list":
        enviar({"id": ident, "result": {"data": [{"id": "gpt-falso", "displayName": "GPT falso", "hidden": False,
                                                   "isDefault": True}], "nextCursor": None}})
    elif met == "thread/start":
        assert p["sandbox"] == "read-only" and p["approvalPolicy"] == "untrusted", p
        threads.add("T1")
        enviar({"id": ident, "result": {"thread": {"id": "T1"}}})
    elif met == "thread/resume":
        if p["threadId"] in threads:
            enviar({"id": ident, "result": {"thread": {"id": p["threadId"]}}})
        else:
            enviar({"id": ident, "error": {"code": -32600, "message": "thread não encontrada"}})
    elif met == "turn/start":
        tid, texto = p["threadId"], p["input"][0]["text"]
        enviar({"id": ident, "result": {"turn": {"id": "U1", "status": "inProgress"}}})
        if "comando" in texto:
            enviar({"id": 900, "method": "item/commandExecution/requestApproval",
                    "params": {"threadId": tid, "turnId": "U1", "itemId": "I1", "startedAtMs": 0,
                               "command": "ls -la", "cwd": "/x", "reason": "ver ficheiros"}})
            r = ler()
            while r.get("id") != 900:
                r = ler()
            decisao = r["result"]["decision"]
            enviar({"method": "item/agentMessage/delta", "params": {"threadId": tid, "turnId": "U1",
                                                                     "itemId": "M1", "delta": f"decisão={decisao}"}})
        else:
            for d in ("Olá ", "do Codex"):
                enviar({"method": "item/agentMessage/delta", "params": {"threadId": tid, "turnId": "U1",
                                                                         "itemId": "M1", "delta": d}})
        enviar({"method": "turn/completed", "params": {"threadId": tid, "turn": {"id": "U1", "status": "completed"}}})
    else:
        enviar({"id": ident, "error": {"code": -32601, "message": f"desconhecido {met}"}})
