"""Fase 5: projectos, documentos, memória, isolamento, agentes e colaboração. Created by Redfox using Claude"""

import time

import pytest


def _proj(c, nome):
    r = c.post("/api/projects", json={"nome": nome, "instrucoes": f"Instruções de {nome}"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _doc(c, pid, nome, texto):
    r = c.post(f"/api/projects/{pid}/documents", files={"ficheiro": (nome, texto.encode(), "text/plain")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_crud_e_documentos(entrar):
    c = entrar()
    pid = _proj(c, "Servidor")
    assert c.patch(f"/api/projects/{pid}", json={"instrucoes": "Responde curto."}).json()["instrucoes"] == "Responde curto."
    did = _doc(c, pid, "notas.md", "A monitorização corre no contentor monitor-web.")
    lst = c.get("/api/projects").json()
    assert lst[0]["documentos"] == 1
    res = c.get(f"/api/projects/{pid}/search", params={"q": "monitorização"}).json()
    assert res["documentos"][0]["id"] == did and "monitorização" in res["documentos"][0]["excerto"]
    assert c.request("DELETE", f"/api/projects/{pid}", json={"confirmar": "errado"}).status_code == 400
    assert c.request("DELETE", f"/api/projects/{pid}", json={"confirmar": "Servidor"}).json() == {"ok": True}
    assert c.get(f"/api/projects/{pid}").status_code == 404


def test_isolamento_entre_projectos(entrar):
    c = entrar()
    a, b = _proj(c, "A"), _proj(c, "B")
    doc_a = _doc(c, a, "segredo.txt", "palavra-unica-do-projecto-a")
    mem_a = c.post(f"/api/projects/{a}/memory", json={"texto": "facto de A"}).json()["id"]
    assert c.get(f"/api/projects/{b}/search", params={"q": "palavra-unica"}).json()["documentos"] == []
    assert c.get(f"/api/projects/{b}/documents").json() == []
    assert c.get(f"/api/projects/{b}/memory").json() == []
    assert c.delete(f"/api/projects/{b}/documents/{doc_a}").status_code == 404
    assert c.delete(f"/api/projects/{b}/memory/{mem_a}").status_code == 404
    assert c.post(f"/api/projects/{b}/memory/{mem_a}/approve").status_code == 404
    # o contexto dado aos modelos também é só do projecto da sessão
    import asyncio

    from app import db
    from app.contexto import contexto_projecto

    async def ctx():
        async for s in db.sessao():
            return await contexto_projecto(s, b)
    texto = asyncio.run(ctx())
    assert "palavra-unica" not in texto and "facto de A" not in texto and "Instruções de B" in texto


def test_memoria_de_agente_fica_pendente(entrar):
    c = entrar()
    pid = _proj(c, "P")
    import asyncio

    from app import db
    from app.rotas_projectos import propor_memoria

    async def propor():
        async for s in db.sessao():
            await propor_memoria(s, pid, "O backup é às 03:00", "agente:Ollama")
            await s.commit()
    asyncio.run(propor())
    m = c.get(f"/api/projects/{pid}/memory").json()[0]
    assert m["aprovada"] is False and m["origem"] == "agente:Ollama"
    from app.contexto import contexto_projecto

    async def ctx():
        async for s in db.sessao():
            return await contexto_projecto(s, pid)
    assert "03:00" not in asyncio.run(ctx())                  # pendente não entra no contexto
    assert c.post(f"/api/projects/{pid}/memory/{m['id']}/approve").json()["aprovada"] is True
    assert "03:00" in asyncio.run(ctx())


def _esperar(c, url, campo="estado", ate=("concluida", "erro"), segundos=10):
    fim = time.time() + segundos
    while time.time() < fim:
        d = c.get(url).json()
        alvo = d[0] if isinstance(d, list) and d else d
        if alvo and alvo.get(campo) in ate:
            return alvo
        time.sleep(0.05)
    pytest.fail(f"timeout em {url}")


@pytest.fixture()
def ollama_memoria(monkeypatch, ollama_falso):
    from app import ollama

    async def conversar(modelo, mensagens):
        pedido = mensagens[-1]["content"]
        if pedido.startswith("Revê"):
            yield "Falta considerar o disco cheio. Acrescentaria monitorização."
        elif pedido.startswith("Consolida"):
            yield "Resposta final consolidada."
        else:
            yield "Análise: o serviço está estável.\nMEMÓRIA: o serviço principal é a aplicação web."
    monkeypatch.setattr(ollama, "conversar", conversar)


def test_agentes_semeados_e_execucao(entrar, ollama_memoria):
    with entrar() as c:
        ags = {a["nome"]: a for a in c.get("/api/agents").json()}
        assert set(ags) == {"Codex", "Claude Code", "Ollama"} and all(a["perfil"] == "so-leitura" for a in ags.values())
        assert c.patch(f"/api/agents/{ags['Ollama']['id']}", json={"perfil": "total"}).status_code == 400
        pid = _proj(c, "P")
        assert c.post(f"/api/agents/{ags['Ollama']['id']}/run", json={"pedido": "Analisa", "projecto_id": pid}).json()
        run = _esperar(c, f"/api/agents/{ags['Ollama']['id']}/runs")
        assert run["estado"] == "concluida" and "estável" in run["saida"]
        mem = c.get(f"/api/projects/{pid}/memory").json()
        assert [(m["texto"], m["aprovada"]) for m in mem] == [("o serviço principal é a aplicação web.", False)]


def test_colaboracao_analise_revisao_consolidacao(entrar, ollama_memoria):
    with entrar() as c:
        o = next(a for a in c.get("/api/agents").json() if a["nome"] == "Ollama")["id"]
        t = c.post("/api/collab", json={"pedido": "O servidor está bem?", "primeiro": o, "segundo": o}).json()
        _esperar(c, f"/api/collab/{t['id']}")
        d = c.get(f"/api/collab/{t['id']}").json()
        assert d["estado"] == "concluida", d
        assert [p["papel"] for p in d["passos"]] == ["analise", "revisao", "consolidacao"]
        assert "Resposta final consolidada." in d["resultado"] and "Semelhança" in d["resultado"]


def test_recuperacao_apos_reinicio(app_teste):
    import asyncio

    from app import db
    from app.models import Agent, AgentRun, CollabTask

    async def preparar():
        async for s in db.sessao():
            a = Agent(name="X", provider="ollama", model="m")
            s.add(a)
            await s.flush()
            s.add(AgentRun(agent_id=a.id, status="a-correr"))
            s.add(CollabTask(prompt="p", first_agent_id=a.id, second_agent_id=a.id, status="a-correr"))
            await s.commit()
    asyncio.run(preparar())
    db._motor = None
    from fastapi.testclient import TestClient
    with TestClient(app_teste) as c:
        r = c.post("/api/auth/login", json={"username": "redfox", "password": "palavra-passe-segura"})
        c.headers["X-CSRF-Token"] = r.json()["csrf"]
        assert c.get("/api/collab").json()[0]["estado"] == "erro"
        x = next(a for a in c.get("/api/agents").json() if a["nome"] == "X")
        assert c.get(f"/api/agents/{x['id']}/runs").json()[0]["estado"] == "erro"
