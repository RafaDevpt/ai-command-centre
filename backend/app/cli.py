"""
Administração pela linha de comandos (dentro do contentor):

  docker compose exec app python -m app.cli criar-utilizador <nome>
  docker compose exec app python -m app.cli repor-senha <nome>

A palavra-passe é pedida sem eco; nunca aparece em argumentos nem em logs.

Created by Redfox using Claude
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from sqlalchemy import select

from .db import motor, sessao
from .models import User
from .seguranca import auditar, hash_senha


def _pedir_senha() -> str:
    s1 = getpass.getpass("Palavra-passe (mín. 12 caracteres): ")
    s2 = getpass.getpass("Repita: ")
    if s1 != s2 or len(s1) < 12:
        sys.exit("As palavras-passe não coincidem ou têm menos de 12 caracteres.")
    return s1


async def _correr(accao: str, nome: str) -> None:
    motor()
    async for s in sessao():
        user = await s.scalar(select(User).where(User.username == nome))
        if accao == "criar-utilizador":
            if user:
                sys.exit("Esse utilizador já existe.")
            s.add(User(username=nome, password_hash=hash_senha(_pedir_senha()), is_admin=True))
            await auditar(s, "cli", "utilizador-criado", username=nome)
        elif accao == "repor-senha":
            if not user:
                sys.exit("Utilizador não encontrado.")
            user.password_hash = hash_senha(_pedir_senha())
            await auditar(s, "cli", "senha-reposta", username=nome)
        else:
            sys.exit(__doc__)
        await s.commit()
        print("Feito.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(_correr(sys.argv[1], sys.argv[2]))
