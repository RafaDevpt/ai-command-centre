"""Fase 6: Claude externo — importação da exportação oficial e registo manual. Created by Redfox using Claude"""

import io
import json
import zipfile

EXPORTACAO = [
    {"uuid": "c-1", "name": "Plano do servidor", "created_at": "2026-10-01T10:00:00Z",
     "updated_at": "2026-10-01T10:05:00Z",
     "chat_messages": [
         {"uuid": "m1", "sender": "human", "text": "Como organizo o Docker?", "created_at": "2026-10-01T10:00:00Z"},
         {"uuid": "m2", "sender": "assistant", "text": "",
          "content": [{"type": "text", "text": "Um projecto Compose por aplicação."}],
          "created_at": "2026-10-01T10:01:00Z"}]},
    {"uuid": "c-2", "name": "", "chat_messages": []},
]


def _zip(dados):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("data-2026/conversations.json", json.dumps(dados))
        z.writestr("data-2026/users.json", "[]")
    return b.getvalue()


def test_importar_zip_oficial_e_sem_repetir(entrar):
    c = entrar()
    r = c.post("/api/claude/import", files={"ficheiro": ("export.zip", _zip(EXPORTACAO), "application/zip")})
    assert r.json() == {"novas": 2, "repetidas": 0, "mensagens": 2}, r.text
    r = c.post("/api/claude/import", files={"ficheiro": ("conversations.json", json.dumps(EXPORTACAO).encode(),
                                                         "application/json")})
    assert r.json()["novas"] == 0 and r.json()["repetidas"] == 2
    lst = c.get("/api/sessions", params={"estado": "externa"}).json()
    s = next(x for x in lst if x["titulo"] == "Plano do servidor")
    assert s["fornecedor"] == "claude-externo"
    d = c.get(f"/api/sessions/{s['id']}").json()
    assert [m["texto"] for m in d["mensagens"]] == ["Como organizo o Docker?", "Um projecto Compose por aplicação."]
    assert c.get("/api/claude/status").json()["sessoes_importadas"] == 2


def test_sessao_importada_e_so_de_leitura(entrar):
    c = entrar()
    c.post("/api/claude/import", files={"ficheiro": ("e.zip", _zip(EXPORTACAO), "application/zip")})
    sid = c.get("/api/sessions", params={"estado": "externa"}).json()[0]["id"]
    with c.websocket_connect("/api/ws/chat", headers={"origin": "http://testserver"}) as ws:
        ws.send_json({"tipo": "enviar", "csrf": c.headers["X-CSRF-Token"], "sessao_id": sid, "texto": "olá",
                      "anexos": []})
        assert ws.receive_json() == {"tipo": "erro", "texto": "Sessão externa: só leitura."}


def test_ficheiros_invalidos(entrar):
    c = entrar()
    assert c.post("/api/claude/import", files={"ficheiro": ("x.zip", b"PK\x03\x04lixo", "application/zip")}).status_code == 400
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("outro.json", "[]")
    assert c.post("/api/claude/import", files={"ficheiro": ("x.zip", b.getvalue(), "application/zip")}).status_code == 400
    assert c.post("/api/claude/import", files={"ficheiro": ("c.json", b'{"a":1}', "application/json")}).status_code == 400


def test_registo_manual_so_aceita_claude_ai(entrar):
    c = entrar()
    assert c.post("/api/claude/sessions", json={"titulo": "x", "ligacao": "https://mau.example/claude.ai"}).status_code == 422
    r = c.post("/api/claude/sessions", json={"titulo": "Revisão do README", "ligacao": "https://claude.ai/chat/abc-123",
                                             "notas": "Decidimos usar PT-PT."})
    d = c.get(f"/api/sessions/{r.json()['id']}").json()
    assert d["estado"] == "externa" and "Decidimos usar PT-PT." in d["mensagens"][0]["texto"]
