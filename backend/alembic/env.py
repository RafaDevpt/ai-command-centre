"""Alembic: usa o mesmo URL da aplicação (socket Unix). Created by Redfox using Claude"""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app import models  # noqa: F401  (regista as tabelas)
from app.config import settings
from app.db import Base

alvo = Base.metadata


def _correr(ligacao):
    context.configure(connection=ligacao, target_metadata=alvo, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    motor = create_async_engine(settings().url_bd())
    async with motor.connect() as ligacao:
        await ligacao.run_sync(_correr)
    await motor.dispose()


if context.is_offline_mode():
    context.configure(url="postgresql+psycopg://", target_metadata=alvo, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online())
