"""Equipa: coordenador divide, membros trabalham em paralelo, coordenador revê e conclui. Created by Redfox using Claude"""

import json
import time

import pytest

from app.equipa import ErroEquipa, ler_json


def test_ler_json_tolerante():
    assert ler_json('Claro!\n```json\n{"estado": "concluido", "x": {"a": 1}}\n```') == {"estado": "concluido",
                                                                                     "x": {"a": 1}}
    assert ler_json('<think>{não}</think> {"a": 2}') == {"a": 2}
    with pytest.raises(ErroEquipa):
        ler_json("sem json nenhum")


def test_validar_aliases_de_campos_do_coordenador():
    from types import SimpleNamespace
    from app.equipa import _subtarefas, _validar

    agente = SimpleNamespace(name="Claude Code")
    plano = {"tasks": [{"member": "Claude Code", "task": "Analisa o erro e apresenta evidências."}]}
    tarefas = _validar(_subtarefas(plano), {"claude code": agente})
    assert tarefas[0]["agente"] is agente
    assert tarefas[0]["instrucoes"] == "Analisa o erro e apresenta evidências."
    assert tarefas[0]["titulo"] == tarefas[0]["instrucoes"]
    dupla = _validar(_subtarefas({"subtasks": [{"agent": "Claude Code", "task": "Verificar o fluxo",
                                                  "instructions": "Inspecciona as condições de corrida."}]}),
                     {"claude code": agente})
    assert dupla[0]["titulo"] == "Verificar o fluxo"
    assert dupla[0]["instrucoes"] == "Inspecciona as condições de corrida."


def test_rejeita_aliases_contraditorios():
    from types import SimpleNamespace
    from app.equipa import _subtarefas, _validar

    agente = SimpleNamespace(name="Claude Code")
    with pytest.raises(ErroEquipa, match="contraditórios"):
        _validar(_subtarefas({"subtasks": [{"agent": "Claude Code", "member": "Ollama",
                                             "instructions": "Analisa."}]}),
                 {"claude code": agente})


def test_cancelamento_do_worker_liberta_a_conversa(monkeypatch):
    import asyncio
    from app import equipa

    recuperada = []

    async def cancelar(*_args, **_kwargs):
        raise asyncio.CancelledError()

    async def recuperar(task_id):
        recuperada.append(task_id)

    monkeypatch.setattr(equipa, "_correr_equipa", cancelar)
    monkeypatch.setattr(equipa, "_recuperar_worker_interrompido", recuperar)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(equipa.correr_equipa("tarefa-interrompida"))
    assert recuperada == ["tarefa-interrompida"]


@pytest.fixture()
def equipa_falsa(monkeypatch, ollama_falso):
    """Todos os agentes são Ollama falsos; o comportamento depende do pedido."""
    from app import ollama
    vistos = []

    async def conversar(modelo, mensagens):
        pedido = mensagens[-1]["content"]
        vistos.append((mensagens[0]["content"], pedido))
        if pedido.startswith("És o coordenador de uma equipa"):
            yield json.dumps({"subtarefas": [
                {"agente": "Programador", "titulo": "Escrever função", "instrucoes": "Escreve soma(a,b)."},
                {"agente": "Basico", "titulo": "Lista de testes", "instrucoes": "Lista casos de teste."}]})
        elif pedido.startswith("És o coordenador. Ronda 1"):
            yield "Vou pedir revisão: " + json.dumps({"estado": "continuar", "subtarefas": [
                {"agente": "Basico", "titulo": "Rever função", "instrucoes": "Revê a função do Programador."}]})
        elif pedido.startswith("És o coordenador. Ronda 2"):
            assert "def soma" in pedido and "Revisão: está correcta." in pedido
            yield json.dumps({"estado": "concluido", "resposta_final": "Função soma pronta e revista."})
        elif "Escreve soma" in pedido:
            yield "def soma(a, b): return a + b"
        elif "Revê a função" in pedido:
            assert "def soma" in pedido            # vê o trabalho do outro membro no quadro
            yield "Revisão: está correcta."
        else:
            yield "1. soma(1,2)=3"
    monkeypatch.setattr(ollama, "conversar", conversar)
    return vistos


def _esperar(c, tid, segundos=10):
    fim = time.time() + segundos
    while time.time() < fim:
        d = c.get(f"/api/team/{tid}").json()
        if d["estado"] not in ("pendente", "a-correr"):
            return d
        time.sleep(0.05)
    pytest.fail("timeout")


def _agentes(c):
    ids = {}
    for nome, papel in (("Coordenador", "planeia"), ("Programador", "código e testes"), ("Basico", "tarefas básicas")):
        r = c.post("/api/agents", json={"nome": nome, "fornecedor": "ollama", "modelo": "qwen3:8b", "papel": papel})
        assert r.status_code == 200, r.text
        ids[nome] = r.json()["id"]
    return ids


def test_equipa_divide_trabalha_e_conclui(entrar, equipa_falsa):
    with entrar() as c:
        ids = _agentes(c)
        t = c.post("/api/team", json={"objectivo": "Uma função soma testada", "coordenador": ids["Coordenador"],
                                      "membros": [ids["Programador"], ids["Basico"]], "rondas": 3}).json()
        d = _esperar(c, t["id"])
        assert d["estado"] == "concluida", d
        assert d["resultado"] == "Função soma pronta e revista." and d["ronda"] == 2
        tipos = [(m["tipo"], m["autor"]) for m in d["quadro"]]
        assert ("subtarefa", "Programador") in tipos and ("subtarefa", "Basico") in tipos
        assert tipos[-1] == ("final", "Coordenador")
        assert all(m["estado"] == "feito" for m in d["quadro"])
        assert any(m["tipo"] == "coordenacao" for m in d["quadro"])
        # o papel de cada agente chega ao modelo
        assert any("O teu papel: código e testes" in sistema for sistema, _ in equipa_falsa)
        assert c.get("/api/team").json()[0]["id"] == t["id"]


def test_ultima_ronda_obriga_a_concluir(entrar, equipa_falsa):
    with entrar() as c:
        ids = _agentes(c)
        t = c.post("/api/team", json={"objectivo": "x", "coordenador": ids["Coordenador"],
                                      "membros": [ids["Programador"], ids["Basico"]], "rondas": 1}).json()
        d = _esperar(c, t["id"])
        assert d["estado"] == "concluida" and d["ronda"] == 1


def test_coordenador_sem_json_da_erro_claro(entrar, monkeypatch, ollama_falso):
    from app import ollama

    async def conversar(modelo, mensagens):
        yield "Não sei responder em JSON."
    monkeypatch.setattr(ollama, "conversar", conversar)
    with entrar() as c:
        ids = _agentes(c)
        t = c.post("/api/team", json={"objectivo": "x", "coordenador": ids["Coordenador"],
                                      "membros": [ids["Basico"]]}).json()
        d = _esperar(c, t["id"])
        assert d["estado"] == "erro" and "JSON" in d["resultado"]


def test_subtarefa_falhada_nao_conclui_equipa(entrar, monkeypatch, ollama_falso):
    from app import ollama
    falhar = True

    async def conversar(modelo, mensagens):
        pedido = mensagens[-1]["content"]
        if pedido.startswith("És o coordenador de uma equipa"):
            yield json.dumps({"subtarefas": [{"agente": "Basico", "titulo": "Tarefa com falha", "instrucoes": "Faz a tarefa."}]})
        elif pedido.startswith("És o coordenador."):
            yield json.dumps({"estado": "concluido", "resposta_final": "Tarefa repetida com sucesso."})
        elif falhar:
            raise RuntimeError("falha simulada do membro")
        else:
            yield "Resultado do membro após a repetição."
    monkeypatch.setattr(ollama, "conversar", conversar)
    with entrar() as c:
        ids = _agentes(c)
        t = c.post("/api/team", json={"objectivo": "x", "coordenador": ids["Coordenador"],
                                      "membros": [ids["Basico"]]}).json()
        d = _esperar(c, t["id"])
        assert d["estado"] == "erro"
        assert "falharam" in d["resultado"]
        assert any(m["estado"] == "erro" for m in d["quadro"] if m["tipo"] == "subtarefa")
        falhar = False
        assert c.post(f"/api/team/{t['id']}/retry").status_code == 200
        repetida = _esperar(c, t["id"])
        assert repetida["estado"] == "concluida"
        assert repetida["resultado"] == "Tarefa repetida com sucesso."


def test_nota_e_parar(entrar, monkeypatch, ollama_falso):
    import asyncio

    from app import ollama

    async def conversar(modelo, mensagens):
        await asyncio.sleep(0.3)
        yield json.dumps({"subtarefas": [{"agente": "Basico", "titulo": "t", "instrucoes": "i"}]})
    monkeypatch.setattr(ollama, "conversar", conversar)
    with entrar() as c:
        ids = _agentes(c)
        t = c.post("/api/team", json={"objectivo": "x", "coordenador": ids["Coordenador"],
                                      "membros": [ids["Basico"]], "rondas": 6}).json()
        assert c.post(f"/api/team/{t['id']}/note", json={"texto": "Usa PT-PT"}).json() == {"ok": True}
        tarefa = c.get(f"/api/team/{t['id']}").json()
        segunda = c.post("/api/team", json={"objectivo": "Mesmo fio", "coordenador": ids["Coordenador"],
                                             "membros": [ids["Basico"]],
                                             "conversation_id": tarefa["conversation_id"]})
        assert segunda.status_code == 409
        c.post(f"/api/team/{t['id']}/stop")
        d = _esperar(c, t["id"])
        assert d["estado"] == "parada"
        assert any(m["tipo"] == "nota" and m["texto"] == "Usa PT-PT" for m in d["quadro"])


def test_criar_e_apagar_agente(entrar):
    c = entrar()
    a = c.post("/api/agents", json={"nome": "Revisor", "fornecedor": "ollama", "modelo": "amalia-9b-ptpt:latest",
                                    "papel": "rever PT-PT"}).json()
    assert a["perfil"] == "so-leitura" and a["papel"] == "rever PT-PT"
    assert c.post("/api/agents", json={"nome": "Revisor", "fornecedor": "ollama"}).status_code == 409
    assert c.post("/api/agents", json={"nome": "X", "fornecedor": "claude"}).status_code == 422
    assert c.delete(f"/api/agents/{a['id']}").json() == {"ok": True}


def test_ponte_claude_briefing_e_retomar(entrar, equipa_falsa, monkeypatch):
    from app import ollama
    with entrar() as c:
        ids = _agentes(c)
        t = c.post("/api/team", json={"objectivo": "Uma função soma testada", "coordenador": ids["Coordenador"],
                                      "membros": [ids["Programador"], ids["Basico"]], "rondas": 3}).json()
        _esperar(c, t["id"])
        b = c.get(f"/api/team/{t['id']}/brief").json()["texto"]
        assert "Uma função soma testada" in b and "def soma" in b and "O que preciso de ti" in b

        vistos = []

        async def conversar(modelo, mensagens):
            vistos.append(mensagens[-1]["content"])
            yield json.dumps({"estado": "concluido", "resposta_final": "Integrei os testes do Claude."})
        monkeypatch.setattr(ollama, "conversar", conversar)
        r = c.post(f"/api/team/{t['id']}/claude", json={"texto": "pytest: 3 passed"}).json()
        assert r == {"ok": True, "retomada": True}
        d = _esperar(c, t["id"])
        assert d["estado"] == "concluida" and d["resultado"] == "Integrei os testes do Claude."
        assert "pytest: 3 passed" in vistos[0] and vistos[0].startswith("És o coordenador. Ronda 3")
        assert any(m["tipo"] == "claude" and m["autor"] == "Claude" for m in d["quadro"])


def test_conversa_continua_memoria_e_isolamento(entrar, monkeypatch, ollama_falso):
    from app import ollama
    pedidos_coordenador = []

    async def conversar(modelo, mensagens):
        pedido = mensagens[-1]["content"]
        if pedido.startswith("És o coordenador de uma equipa"):
            yield json.dumps({"subtasks": [{"member": "Basico", "task": "Executa a análise."}]})
        elif pedido.startswith("És o coordenador."):
            pedidos_coordenador.append(pedido)
            yield json.dumps({"estado": "concluido", "resposta_final": "Resposta do turno."})
        else:
            yield "Resultado partilhável do membro."
    monkeypatch.setattr(ollama, "conversar", conversar)
    with entrar() as c:
        ids = _agentes(c)
        payload = {"objectivo": "Primeiro pedido contínuo", "coordenador": ids["Coordenador"],
                   "membros": [ids["Basico"]], "rondas": 1}
        primeiro = c.post("/api/team", json=payload).json()
        assert primeiro["conversation_id"]
        _esperar(c, primeiro["id"])
        cid = primeiro["conversation_id"]
        assert c.patch(f"/api/team/conversations/{cid}/memory",
                       json={"texto": "A utilizadora prefere respostas concisas."}).status_code == 200
        payload.update(objectivo="Segundo pedido do mesmo fio", conversation_id=cid)
        segundo = c.post("/api/team", json=payload)
        assert segundo.status_code == 200, segundo.text
        _esperar(c, segundo.json()["id"])
        detalhe = c.get(f"/api/team/conversations/{cid}").json()
        assert len(detalhe["tarefas"]) == 2
        assert [x["turno"] for x in detalhe["tarefas"]] == [1, 2]
        assert detalhe["memoria"] == "A utilizadora prefere respostas concisas."
        assert "Primeiro pedido contínuo" in pedidos_coordenador[-1]
        assert "A utilizadora prefere respostas concisas." in pedidos_coordenador[-1]
        outra = c.post("/api/team", json={**payload, "objectivo": "Fio isolado", "conversation_id": None}).json()
        _esperar(c, outra["id"])
        assert "Primeiro pedido contínuo" not in pedidos_coordenador[-1]
