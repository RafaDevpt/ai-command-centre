"""
Projectos: instruções, documentos (texto extraído), memória e pesquisa.
Cada rota confirma que o objecto pertence ao projecto do URL (isolamento).
A memória proposta por agentes fica pendente até o utilizador aprovar.

Created by Redfox using Claude
"""

from __future__ import annotations

import math
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import ollama
from .config import settings
from .db import sessao
from .models import ChatSession, MemoryItem, Project, ProjectDocument
from .seguranca import Autenticado, auditar, autenticado

r = APIRouter(prefix="/api", tags=["projectos"])
MAX_DOC = 10 * 1024 * 1024
MODELO_EMBED = "nomic-embed-text:latest"


class NovoProjecto(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    instrucoes: str = Field(default="", max_length=20000)


class MudarProjecto(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    instrucoes: str | None = Field(default=None, max_length=20000)


class Apagar(BaseModel):
    confirmar: str


class NovaMemoria(BaseModel):
    tipo: str = Field(default="nota", pattern="^(nota|resumo|documento)$")
    texto: str = Field(min_length=1, max_length=8000)


def _p(p: Project, extra: dict | None = None) -> dict:
    return {"id": p.id, "nome": p.name, "instrucoes": p.instructions,
            "criado": p.created_at.isoformat() if p.created_at else None, **(extra or {})}


def _m(m: MemoryItem) -> dict:
    return {"id": m.id, "tipo": m.kind, "texto": m.content, "origem": m.source, "aprovada": m.approved,
            "indexada": bool(m.embedding), "criada": m.created_at.isoformat() if m.created_at else None}


async def _projecto(s: AsyncSession, ident: str) -> Project:
    p = await s.get(Project, ident)
    if not p:
        raise HTTPException(404, "Projecto não encontrado.")
    return p


def _pasta(ident: str):
    return settings().data_dir / "projects" / ident


@r.get("/projects")
async def listar(s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    ps = (await s.scalars(select(Project).order_by(Project.name))).all()
    conta = dict((await s.execute(select(ChatSession.project_id, func.count()).group_by(ChatSession.project_id))).all())
    docs = dict((await s.execute(select(ProjectDocument.project_id, func.count())
                                 .group_by(ProjectDocument.project_id))).all())
    pend = dict((await s.execute(select(MemoryItem.project_id, func.count()).where(MemoryItem.approved.is_(False))
                                 .group_by(MemoryItem.project_id))).all())
    return [_p(p, {"sessoes": conta.get(p.id, 0), "documentos": docs.get(p.id, 0),
                   "memoria_pendente": pend.get(p.id, 0)}) for p in ps]


@r.post("/projects")
async def criar(d: NovoProjecto, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    p = Project(name=d.nome.strip(), instructions=d.instrucoes)
    s.add(p)
    await s.flush()
    _pasta(p.id).mkdir(parents=True, exist_ok=True)
    await auditar(s, u.user.username, "projecto-criado", projecto=p.id)
    await s.commit()
    return _p(p)


@r.get("/projects/{ident}")
async def ver(ident: str, s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    p = await _projecto(s, ident)
    sess = (await s.scalars(select(ChatSession).where(ChatSession.project_id == p.id)
                            .order_by(ChatSession.last_activity.desc()).limit(50))).all()
    return _p(p, {"sessoes": [{"id": x.id, "titulo": x.title, "fornecedor": x.provider, "modelo": x.model,
                               "estado": x.status, "ultima": x.last_activity.isoformat() if x.last_activity else None}
                              for x in sess]})


@r.patch("/projects/{ident}")
async def mudar(ident: str, d: MudarProjecto, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    p = await _projecto(s, ident)
    if d.nome is not None:
        p.name = d.nome.strip()
    if d.instrucoes is not None:
        p.instructions = d.instrucoes
    await auditar(s, u.user.username, "projecto-alterado", projecto=p.id)
    await s.commit()
    return _p(p)


@r.delete("/projects/{ident}")
async def apagar(ident: str, d: Apagar, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    """Apaga da BD (documentos e memória incluídos). As sessões ficam, sem projecto.
    Os ficheiros em projects/<id> não são apagados: ficam para cópia/limpeza manual."""
    p = await _projecto(s, ident)
    if d.confirmar != p.name:
        raise HTTPException(400, "Escreva o nome do projecto para confirmar.")
    await s.execute(delete(ProjectDocument).where(ProjectDocument.project_id == p.id))
    await s.execute(delete(MemoryItem).where(MemoryItem.project_id == p.id))
    for x in (await s.scalars(select(ChatSession).where(ChatSession.project_id == p.id))).all():
        x.project_id = None
    await s.delete(p)
    await auditar(s, u.user.username, "projecto-apagado", projecto=ident)
    await s.commit()
    return {"ok": True}


# --- documentos -------------------------------------------------------------------

def _texto(dados: bytes, nome: str) -> str:
    if b"\x00" in dados[:4096]:
        return ""                                    # binário: guarda-se, mas sem texto
    for cod in ("utf-8", "latin-1"):
        try:
            return dados.decode(cod)[:500_000]
        except UnicodeDecodeError:
            continue
    return ""


@r.get("/projects/{ident}/documents")
async def documentos(ident: str, s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    p = await _projecto(s, ident)
    ds = (await s.scalars(select(ProjectDocument).where(ProjectDocument.project_id == p.id)
                          .order_by(ProjectDocument.id.desc()))).all()
    return [{"id": d.id, "nome": d.filename, "tamanho": d.size, "tem_texto": bool(d.text),
             "criado": d.created_at.isoformat() if d.created_at else None} for d in ds]


@r.post("/projects/{ident}/documents")
async def carregar(ident: str, ficheiro: UploadFile, s: AsyncSession = Depends(sessao),
                   u: Autenticado = Depends(autenticado)):
    p = await _projecto(s, ident)
    dados = await ficheiro.read(MAX_DOC + 1)
    if len(dados) > MAX_DOC:
        raise HTTPException(413, "Documento maior do que 10 MB.")
    nome = re.sub(r"[^\w.\- ]", "_", (ficheiro.filename or "documento").rsplit("/", 1)[-1])[:120] or "documento"
    pasta = _pasta(p.id) / "docs"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{secrets.token_hex(6)}_{nome}"
    destino.write_bytes(dados)
    destino.chmod(0o600)
    d = ProjectDocument(project_id=p.id, filename=nome, path=str(destino), size=len(dados), text=_texto(dados, nome))
    s.add(d)
    await auditar(s, u.user.username, "documento-carregado", projecto=p.id, nome=nome)
    await s.commit()
    return {"id": d.id, "nome": nome, "tamanho": d.size, "tem_texto": bool(d.text)}


@r.delete("/projects/{ident}/documents/{doc}")
async def apagar_doc(ident: str, doc: int, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    d = await s.get(ProjectDocument, doc)
    if not d or d.project_id != ident:
        raise HTTPException(404, "Documento não encontrado neste projecto.")
    await s.delete(d)
    await auditar(s, u.user.username, "documento-removido", projecto=ident, nome=d.filename)
    await s.commit()
    return {"ok": True}


def _excerto(texto: str, termo: str, largura: int = 120) -> str:
    i = texto.lower().find(termo.lower())
    if i < 0:
        return texto[:largura * 2]
    return ("…" if i > largura else "") + texto[max(0, i - largura): i + len(termo) + largura] + "…"


@r.get("/projects/{ident}/search")
async def procurar(ident: str, q: str, s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    """Pesquisa nos documentos e na memória deste projecto (só deste)."""
    p = await _projecto(s, ident)
    q = q.strip()[:200]
    if not q:
        return {"documentos": [], "memoria": []}
    padrao = f"%{q}%"
    ds = (await s.scalars(select(ProjectDocument).where(ProjectDocument.project_id == p.id,
                                                        or_(ProjectDocument.text.ilike(padrao),
                                                            ProjectDocument.filename.ilike(padrao))).limit(20))).all()
    ms = (await s.scalars(select(MemoryItem).where(MemoryItem.project_id == p.id,
                                                   MemoryItem.content.ilike(padrao)).limit(20))).all()
    return {"documentos": [{"id": d.id, "nome": d.filename, "excerto": _excerto(d.text, q)} for d in ds],
            "memoria": [_m(m) for m in ms]}


# --- memória ------------------------------------------------------------------------

@r.get("/projects/{ident}/memory")
async def memoria(ident: str, s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    p = await _projecto(s, ident)
    ms = (await s.scalars(select(MemoryItem).where(MemoryItem.project_id == p.id).order_by(MemoryItem.id.desc()))).all()
    return [_m(m) for m in ms]


@r.post("/projects/{ident}/memory")
async def nova_memoria(ident: str, d: NovaMemoria, s: AsyncSession = Depends(sessao),
                       u: Autenticado = Depends(autenticado)):
    p = await _projecto(s, ident)
    m = MemoryItem(project_id=p.id, kind=d.tipo, content=d.texto, source=u.user.username, approved=True)
    s.add(m)
    await s.commit()
    return _m(m)


async def _item(s: AsyncSession, ident: str, mem: int) -> MemoryItem:
    m = await s.get(MemoryItem, mem)
    if not m or m.project_id != ident:
        raise HTTPException(404, "Memória não encontrada neste projecto.")
    return m


@r.post("/projects/{ident}/memory/{mem}/approve")
async def aprovar_memoria(ident: str, mem: int, s: AsyncSession = Depends(sessao),
                          u: Autenticado = Depends(autenticado)):
    m = await _item(s, ident, mem)
    m.approved = True
    await auditar(s, u.user.username, "memoria-aprovada", projecto=ident, memoria=m.id, origem=m.source)
    await s.commit()
    return _m(m)


@r.delete("/projects/{ident}/memory/{mem}")
async def apagar_memoria(ident: str, mem: int, s: AsyncSession = Depends(sessao),
                         u: Autenticado = Depends(autenticado)):
    m = await _item(s, ident, mem)
    await s.delete(m)
    await auditar(s, u.user.username, "memoria-removida", projecto=ident, memoria=mem)
    await s.commit()
    return {"ok": True}


@r.post("/projects/{ident}/memory/index")
async def indexar(ident: str, s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    """Embeddings a pedido (nomic-embed-text, já instalado no Ollama). Nunca descarrega modelos."""
    p = await _projecto(s, ident)
    if MODELO_EMBED not in [m["id"] for m in await ollama.modelos()]:
        raise HTTPException(409, f"O modelo {MODELO_EMBED} não está instalado no Ollama.")
    ms = (await s.scalars(select(MemoryItem).where(MemoryItem.project_id == p.id, MemoryItem.approved.is_(True),
                                                   MemoryItem.embedding.is_(None)).limit(200))).all()
    for m in ms:
        m.embedding = await ollama.embedding(m.content, MODELO_EMBED)
    await s.commit()
    return {"indexadas": len(ms)}


def _cos(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb) if na and nb else 0.0


@r.get("/projects/{ident}/memory/similar")
async def semelhantes(ident: str, q: str, s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    p = await _projecto(s, ident)
    ms = (await s.scalars(select(MemoryItem).where(MemoryItem.project_id == p.id, MemoryItem.approved.is_(True),
                                                   MemoryItem.embedding.is_not(None)))).all()
    if not ms:
        return []
    v = await ollama.embedding(q[:2000], MODELO_EMBED)
    return sorted(({**_m(m), "pontuacao": round(_cos(v, m.embedding), 3)} for m in ms),
                  key=lambda x: -x["pontuacao"])[:10]


async def propor_memoria(s: AsyncSession, projecto_id: str, texto: str, origem: str) -> None:
    """Usado pelos agentes: fica pendente (approved=False) até o utilizador aprovar."""
    s.add(MemoryItem(project_id=projecto_id, kind="nota", content=texto[:4000], source=origem[:80], approved=False))
