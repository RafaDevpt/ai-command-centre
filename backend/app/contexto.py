"""
Contexto partilhado com os agentes: instruções do projecto, memória aprovada
e excertos dos documentos, com um limite de tamanho (CPU, contexto 4096).

Created by Redfox using Claude
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import MemoryItem, Project, ProjectDocument

MAX_CONTEXTO = 6000   # caracteres (~1500 tokens)


async def contexto_projecto(s: AsyncSession, projecto_id: str | None) -> str:
    if not projecto_id:
        return ""
    p = await s.get(Project, projecto_id)
    if p is None:
        return ""
    partes = [f"Projecto: {p.name}"]
    if p.instructions.strip():
        partes.append("Instruções do projecto:\n" + p.instructions.strip())
    memoria = (await s.scalars(select(MemoryItem).where(MemoryItem.project_id == p.id, MemoryItem.approved.is_(True))
                               .order_by(MemoryItem.id.desc()).limit(20))).all()
    if memoria:
        partes.append("Memória aprovada:\n" + "\n".join(f"- [{m.kind}] {m.content[:400]}" for m in memoria))
    docs = (await s.scalars(select(ProjectDocument).where(ProjectDocument.project_id == p.id)
                            .order_by(ProjectDocument.id.desc()).limit(5))).all()
    for d in docs:
        if d.text:
            partes.append(f"Documento «{d.filename}» (excerto):\n{d.text[:1500]}")
    return "\n\n".join(partes)[:MAX_CONTEXTO]
