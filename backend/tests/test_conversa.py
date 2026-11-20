"""Fase 3: sessões, conversa com Ollama (falso), persistência, pesquisa, anexos e WebSocket. Created by Redfox using Claude"""


def _nova(c, **extra):
    r = c.post("/api/sessions", json={"fornecedor": "ollama", "modelo": "qwen3:8b", **extra})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _enviar_ws(c, sid, texto, anexos=()):
    eventos = []
    with c.websocket_connect("/api/ws/chat", headers={"origin": "http://testserver"}) as ws:
        ws.send_json({"tipo": "enviar", "csrf": c.headers["X-CSRF-Token"], "sessao_id": sid,
                      "texto": texto, "anexos": list(anexos)})
        while True:
            e = ws.receive_json()
            eventos.append(e)
            if e["tipo"] in ("fim", "erro"):
                break
    return eventos


def test_modelos(entrar, ollama_falso):
    assert entrar().get("/api/models").json()[0]["id"] == "qwen3:8b"


def test_conversa_streaming_e_persistencia(entrar, ollama_falso):
    c = entrar()
    sid = _nova(c)
    eventos = _enviar_ws(c, sid, "Olá, servidor")
    assert [e["tipo"] for e in eventos] == ["delta", "delta", "fim"]
    assert eventos[-1]["fornecedor"] == "ollama" and eventos[-1]["modelo"] == "qwen3:8b"
    d = c.get(f"/api/sessions/{sid}").json()
    assert d["titulo"] == "Olá, servidor"
    assert [(m["papel"], m["fornecedor"]) for m in d["mensagens"]] == [("user", None), ("assistant", "ollama")]
    assert d["mensagens"][1]["texto"] == "Olá (2 mensagens)"   # sistema + utilizador


def test_retomar_sessao_envia_historico(entrar, ollama_falso):
    c = entrar()
    sid = _nova(c)
    _enviar_ws(c, sid, "primeira")
    _enviar_ws(c, sid, "segunda")
    _, mensagens = ollama_falso[-1]
    assert [m["role"] for m in mensagens] == ["system", "user", "assistant", "user"]


def test_pesquisa_no_historico(entrar, ollama_falso):
    c = entrar()
    sid = _nova(c)
    _enviar_ws(c, sid, "fala-me de girassóis")
    _nova(c)
    assert [x["id"] for x in c.get("/api/sessions", params={"q": "girassóis"}).json()] == [sid]


def test_anexo_de_texto_vai_para_o_contexto(entrar, ollama_falso):
    c = entrar()
    a = c.post("/api/attachments", files={"ficheiro": ("notas.md", b"conteudo-secreto-do-anexo", "text/markdown")}).json()
    assert a["texto"] is True
    sid = _nova(c)
    _enviar_ws(c, sid, "resume o anexo", [a])
    _, mensagens = ollama_falso[-1]
    assert "conteudo-secreto-do-anexo" in mensagens[-1]["content"]


def test_websocket_recusa_sem_sessao_ou_outra_origem(cliente, entrar):
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with cliente.websocket_connect("/api/ws/chat") as ws:
            ws.receive_json()
    c = entrar()
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/api/ws/chat", headers={"origin": "http://evil.example"}) as ws:
            ws.receive_json()


def test_websocket_csrf(entrar, ollama_falso):
    c = entrar()
    sid = _nova(c)
    with c.websocket_connect("/api/ws/chat", headers={"origin": "http://testserver"}) as ws:
        ws.send_json({"tipo": "enviar", "csrf": "errado", "sessao_id": sid, "texto": "x"})
        assert ws.receive_json() == {"tipo": "erro", "texto": "CSRF inválido."}


def test_sessao_com_projecto_inexistente(entrar):
    assert entrar().post("/api/sessions", json={"fornecedor": "ollama", "modelo": "m",
                                               "projecto_id": "nao-existe"}).status_code == 404
