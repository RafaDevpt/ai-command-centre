"""Fase 1: saúde e servir o frontend. Created by Redfox using Claude"""


def test_vivo(cliente):
    r = cliente.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["X-Frame-Options"] == "DENY" and "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_pronto_com_ollama_em_baixo(cliente, monkeypatch):
    from app import main

    async def ollama_off():
        return {"ok": False, "erro": "ConnectError"}
    monkeypatch.setattr(main, "estado_ollama", ollama_off)
    r = cliente.get("/api/health/ready")
    assert r.status_code == 200 and r.json()["bd"]["ok"] and not r.json()["ollama"]["ok"]


def test_spa_nao_sai_da_pasta(cliente, app_teste):
    from app.config import settings
    raiz = settings().static_dir
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "index.html").write_text("<html>spa</html>")
    assert "spa" in cliente.get("/qualquer/rota").text
    assert "spa" in cliente.get("/../../etc/passwd").text
    assert cliente.get("/api/inexistente").status_code == 404
