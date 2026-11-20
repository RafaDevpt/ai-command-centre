"""Ligação assíncrona ao PostgreSQL (SQLAlchemy 2). Created by Redfox using Claude"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

_motor: AsyncEngine | None = None
_sessoes: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    pass


def motor() -> AsyncEngine:
    global _motor, _sessoes
    if _motor is None:
        # pool pequeno: aplicação de um só utilizador num servidor partilhado
        _motor = create_async_engine(settings().url_bd(), pool_size=5, max_overflow=5, pool_pre_ping=True)
        _sessoes = async_sessionmaker(_motor, expire_on_commit=False)
    return _motor


async def sessao() -> AsyncIterator[AsyncSession]:
    motor()
    async with _sessoes() as s:  # type: ignore[misc]
        yield s
