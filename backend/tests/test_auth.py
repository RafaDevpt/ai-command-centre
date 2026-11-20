"""Fase 2: login, sessões, CSRF, limite de tentativas. Created by Redfox using Claude"""


def test_rotas_protegidas_sem_sessao(cliente):
    assert cliente.get("/api/dashboard").status_code == 401
    assert cliente.get("/api/sessions").status_code == 401
    for url in ("/api/projects", "/api/agents", "/api/collab", "/api/approvals", "/api/audit", "/api/codex/status",
                "/api/models", "/api/projects/x/memory"):
        assert cliente.get(url).status_code == 401, url


def test_escrita_exige_csrf(entrar):
    c = entrar()
    token = c.headers.pop("X-CSRF-Token")
    assert c.post("/api/projects", json={"nome": "x"}).status_code == 403
    assert c.post("/api/approvals/abc", json={"decisao": "aprovar"}).status_code == 403
    c.headers["X-CSRF-Token"] = token
    assert c.post("/api/projects", json={"nome": "x"}).status_code == 200


def test_login_certo_e_cookie_seguro(cliente):
    r = cliente.post("/api/auth/login", json={"username": "redfox", "password": "palavra-passe-segura"})
    assert r.status_code == 200 and r.json()["csrf"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "palavra-passe" not in r.text


def test_login_errado_e_limite_de_tentativas(cliente):
    for _ in range(5):
        assert cliente.post("/api/auth/login", json={"username": "redfox", "password": "errada"}).status_code == 401
    r = cliente.post("/api/auth/login", json={"username": "redfox", "password": "palavra-passe-segura"})
    assert r.status_code == 429


def test_csrf_obrigatorio_em_alteracoes(entrar):
    c = entrar()
    token = c.headers.pop("X-CSRF-Token")
    assert c.post("/api/auth/logout").status_code == 403
    c.headers["X-CSRF-Token"] = "errado"
    assert c.post("/api/auth/logout").status_code == 403
    c.headers["X-CSRF-Token"] = token
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401


def test_mudar_senha(entrar):
    c = entrar()
    assert c.post("/api/auth/password", json={"atual": "errada", "nova": "outra-palavra-longa"}).status_code == 400
    assert c.post("/api/auth/password", json={"atual": "palavra-passe-segura", "nova": "curta"}).status_code == 422
    assert c.post("/api/auth/password", json={"atual": "palavra-passe-segura",
                                              "nova": "nova-palavra-passe-longa"}).status_code == 200
    c.post("/api/auth/logout")
    assert c.post("/api/auth/login", json={"username": "redfox", "password": "nova-palavra-passe-longa"}).status_code == 200


def test_painel(entrar, ollama_falso):
    d = entrar().get("/api/dashboard").json()
    assert set(d) >= {"fornecedores", "ollama", "sessoes_recentes", "aprovacoes_pendentes", "recursos"}
    assert d["fornecedores"]["claude"]["externo"] is True


def test_auditoria_regista_login(entrar, app_teste):
    import asyncio
    from sqlalchemy import select
    from app import db, models
    entrar()

    async def ler():
        async for s in db.sessao():
            return [x.action for x in (await s.scalars(select(models.AuditLog))).all()]
    assert "login" in asyncio.run(ler())
