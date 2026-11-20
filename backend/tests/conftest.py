"""Base de testes: SQLite temporário, utilizador de teste e cliente autenticado. Created by Redfox using Claude"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def app_teste(tmp_path, monkeypatch):
    monkeypatch.setenv("AICC_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("AICC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AICC_STATIC_DIR", str(tmp_path / "static"))
    from app import config, db
    config.settings.cache_clear()
    db._motor = None
    db._sessoes = None
    from app import main, models  # noqa: F401

    async def criar():
        async with db.motor().begin() as c:
            await c.run_sync(db.Base.metadata.create_all)
        async for s in db.sessao():
            from app.seguranca import hash_senha
            s.add(models.User(username="redfox", password_hash=hash_senha("palavra-passe-segura")))
            await s.commit()
    asyncio.run(criar())
    main.app.dependency_overrides.clear()
    yield main.app
    asyncio.run(db.motor().dispose())
    db._motor = None
    config.settings.cache_clear()


@pytest.fixture()
def cliente(app_teste):
    from fastapi.testclient import TestClient
    return TestClient(app_teste)


@pytest.fixture()
def entrar(cliente):
    def _entrar():
        r = cliente.post("/api/auth/login", json={"username": "redfox", "password": "palavra-passe-segura"})
        assert r.status_code == 200, r.text
        cliente.headers["X-CSRF-Token"] = r.json()["csrf"]
        return cliente
    return _entrar


@pytest.fixture()
def ollama_falso(monkeypatch):
    """Ollama falso: responde com o número de mensagens recebidas, em dois pedaços."""
    from app import ollama
    vistas = []

    async def conversar(modelo, mensagens):
        vistas.append((modelo, mensagens))
        yield "Olá "
        yield f"({len(mensagens)} mensagens)"

    async def modelos():
        return [{"id": "qwen3:8b", "fornecedor": "ollama", "nome": "qwen3:8b", "tamanho": 5_200_000_000,
                 "carregado": False, "conversa": True}]
    monkeypatch.setattr(ollama, "conversar", conversar)
    monkeypatch.setattr(ollama, "modelos", modelos)
    return vistas
