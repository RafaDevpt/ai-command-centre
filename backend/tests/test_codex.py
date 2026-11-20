"""Fase 4: adaptador do Codex (app-server falso), login, conversa e aprovações. Created by Redfox using Claude"""

import stat
import sys
from pathlib import Path

import pytest

FALSO = Path(__file__).parent / "falsos" / "codex_falso.py"


@pytest.fixture()
def codex_falso(app_teste, tmp_path, monkeypatch):
    exe = tmp_path / "bin" / "codex-app-server"
    exe.parent.mkdir()
    exe.write_text(f"#!{sys.executable}\nimport runpy; runpy.run_path({str(FALSO)!r}, run_name='__main__')\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    from app import codex
    g = codex.GestorCodex(binario=exe, codex_home=tmp_path / "codex-home")
    monkeypatch.setattr(codex, "_gestor", g)
    return g


def test_sem_login_e_sem_tokens(entrar, codex_falso):
    with entrar() as c:
        e = c.get("/api/codex/status").json()
        assert e["instalado"] and not e["ok"] and e["nota"] == "Sem sessão iniciada."
        assert (codex_falso.home.stat().st_mode & 0o777) == 0o700


def test_login_por_codigo_e_logout(entrar, codex_falso):
    with entrar() as c:
        d = c.post("/api/codex/login").json()
        assert d == {"login_id": "L1", "url": "https://auth.openai.com/codex/device", "codigo": "ABCD-1234"}
        codex_falso._cache_estado = None
        e = c.get("/api/codex/status").json()
        assert e["ok"] and e["plano"] == "go" and e["conta"] == "r***@example.com"
        assert "redfox@example.com" not in str(e)
        assert c.post("/api/codex/logout").json() == {"ok": True}
        assert not c.get("/api/codex/status").json()["ok"]


def test_rotas_codex_exigem_login(cliente, codex_falso):
    assert cliente.get("/api/codex/status").status_code == 401
    assert cliente.post("/api/codex/login").status_code in (401, 403)


def _ws(c, sid, texto, ao_pedir=None):
    eventos = []
    with c.websocket_connect("/api/ws/chat", headers={"origin": "http://testserver"}) as ws:
        ws.send_json({"tipo": "enviar", "csrf": c.headers["X-CSRF-Token"], "sessao_id": sid, "texto": texto,
                      "anexos": []})
        while True:
            e = ws.receive_json()
            eventos.append(e)
            if e["tipo"] == "aprovacao" and ao_pedir:
                ao_pedir(e)
            if e["tipo"] in ("fim", "erro"):
                return eventos


def _sessao_codex(c, codex_falso):
    (codex_falso.home).mkdir(parents=True, exist_ok=True)
    (codex_falso.home / "sessao-falsa").write_text("x")
    r = c.post("/api/sessions", json={"fornecedor": "codex", "modelo": "gpt-falso"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_conversa_codex_guarda_thread(entrar, codex_falso):
    with entrar() as c:
        sid = _sessao_codex(c, codex_falso)
        ev = _ws(c, sid, "Olá")
        assert "".join(e["texto"] for e in ev if e["tipo"] == "delta") == "Olá do Codex"
        assert ev[-1]["fornecedor"] == "codex" and ev[-1]["erro"] is None
        ev = _ws(c, sid, "Outra vez")            # retoma a mesma thread
        assert not [e for e in ev if e["tipo"] == "aviso"]
        d = c.get(f"/api/sessions/{sid}").json()
        assert [m["papel"] for m in d["mensagens"]] == ["user", "assistant", "user", "assistant"]


@pytest.mark.parametrize("decisao,esperado,estado", [("aprovar", "accept", "aprovada"),
                                                      ("rejeitar", "decline", "rejeitada")])
def test_pedido_de_comando_passa_pelas_aprovacoes(entrar, codex_falso, decisao, esperado, estado):
    with entrar() as c:
        sid = _sessao_codex(c, codex_falso)
        vistos = []

        def decidir(e):
            pend = c.get("/api/approvals", params={"estado": "pendente"}).json()
            assert pend["pendentes"] == 1 and pend["itens"][0]["tipo"] == "comando"
            assert pend["itens"][0]["detalhe"]["comando"] == "ls -la"
            vistos.append(e["id"])
            assert c.post(f"/api/approvals/{e['id']}", json={"decisao": decisao}).status_code == 200
        ev = _ws(c, sid, "corre um comando", decidir)
        assert vistos
        assert "".join(e["texto"] for e in ev if e["tipo"] == "delta") == f"decisão={esperado}"
        a = c.get(f"/api/approvals/{vistos[0]}").json()
        assert a["estado"] == estado and a["decidida_por"] == "redfox"
        assert c.post(f"/api/approvals/{vistos[0]}", json={"decisao": "aprovar"}).status_code == 409
        accoes = [x["accao"] for x in c.get("/api/audit").json()]
        assert "aprovacao-pedida" in accoes and f"aprovacao-{estado}" in accoes


def test_aprovacoes_orfas_expiram_no_arranque(app_teste):
    import asyncio

    from app import aprovacoes, db
    from app.models import Approval

    async def preparar():
        await aprovacoes.criar("codex", "comando", "x", {}, None)
    asyncio.run(preparar())
    db._motor = None
    from fastapi.testclient import TestClient
    with TestClient(app_teste):
        pass

    async def ver():
        async for s in db.sessao():
            from sqlalchemy import select
            return (await s.scalars(select(Approval))).one().status
    assert asyncio.run(ver()) == "expirada"


def test_ponte_por_socket_unix(app_teste, codex_falso, tmp_path):
    """Produção: o app-server corre noutro contentor, atrás de ponte_codex.py."""
    import asyncio
    import os
    import subprocess
    import time

    from app import codex
    sock = tmp_path / "s" / "codex.sock"
    sock.parent.mkdir()
    env = {**os.environ, "AICC_CODEX_SOCKET": str(sock), "AICC_CODEX_BIN": str(codex_falso.binario),
           "CODEX_HOME": str(tmp_path / "home-ponte"), "AICC_CODEX_LOG": str(tmp_path / "ponte.log")}
    p = subprocess.Popen([sys.executable, "-m", "app.ponte_codex"], cwd=Path(__file__).parent.parent, env=env)
    try:
        for _ in range(50):
            if sock.exists():
                break
            time.sleep(0.1)
        assert (sock.stat().st_mode & 0o077) == 0      # só o dono

        async def correr():
            g = codex.GestorCodex(socket=sock)
            assert g.instalado
            e = await g.estado()
            m = await g.modelos()
            await g.parar()
            return e, m
        e, m = asyncio.run(correr())
        assert e["instalado"] and not e["ok"] and m[0]["id"] == "gpt-falso"
    finally:
        p.terminate()
        p.wait(5)
