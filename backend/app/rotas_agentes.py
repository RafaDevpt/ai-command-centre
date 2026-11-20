"""Rotas de agentes, execuções e colaboração. Created by Redfox using Claude"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import agentes, equipa
from .db import sessao
from .models import Agent, AgentRun, CollabTask, Project, TeamConversation, TeamMessage, TeamTask
from .seguranca import Autenticado, agora, auditar, autenticado

r = APIRouter(prefix="/api", tags=["agentes"])


class NovoAgente(BaseModel):
    nome: str = Field(min_length=1, max_length=80, pattern=r"^[\w À-ÿ.\-]+$")
    fornecedor: str = Field(pattern="^(ollama|codex|claude-code)$")
    modelo: str = Field(default="", max_length=120)
    papel: str = Field(default="", max_length=2000)


class MudarAgente(BaseModel):
    papel: str | None = Field(default=None, max_length=2000)
    modelo: str | None = Field(default=None, max_length=120)
    activo: bool | None = None
    perfil: str | None = None


class Pedido(BaseModel):
    pedido: str = Field(min_length=1, max_length=20000)
    projecto_id: str | None = None


class NovaColaboracao(Pedido):
    primeiro: str
    segundo: str


def _a(a: Agent) -> dict:
    return {"id": a.id, "nome": a.name, "fornecedor": a.provider, "modelo": a.model or None,
            "capacidades": a.capabilities, "papel": a.role, "perfil": a.permission_profile, "activo": a.enabled}


def _run(x: AgentRun) -> dict:
    return {"id": x.id, "agente_id": x.agent_id, "tarefa_id": x.task_id, "papel": x.role, "estado": x.status,
            "saida": x.output, "inicio": x.started_at.isoformat() if x.started_at else None,
            "fim": x.finished_at.isoformat() if x.finished_at else None}


def _t(t: CollabTask, runs: list[AgentRun] | None = None) -> dict:
    d = {"id": t.id, "pedido": t.prompt, "projecto_id": t.project_id, "primeiro": t.first_agent_id,
         "segundo": t.second_agent_id, "estado": t.status, "resultado": t.result,
         "criada": t.created_at.isoformat() if t.created_at else None,
         "fim": t.finished_at.isoformat() if t.finished_at else None}
    if runs is not None:
        d["passos"] = [_run(x) for x in runs]
    return d


async def _projecto_valido(s: AsyncSession, ident: str | None) -> None:
    if ident and not await s.get(Project, ident):
        raise HTTPException(404, "Projecto não encontrado.")


async def _verificar_dono_conversa(s: AsyncSession, t: TeamTask, u: Autenticado) -> None:
    if t.conversation_id:
        c = await s.get(TeamConversation, t.conversation_id)
        if not c or c.owner_id not in (None, u.user.id):
            raise HTTPException(404, "Tarefa não encontrada.")


@r.get("/agents")
async def listar(s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    return [_a(a) for a in (await s.scalars(select(Agent).order_by(Agent.name))).all()]


@r.post("/agents")
async def criar(d: NovoAgente, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    if await s.scalar(select(Agent).where(Agent.name == d.nome.strip())):
        raise HTTPException(409, "Já existe um agente com esse nome.")
    a = Agent(name=d.nome.strip(), provider=d.fornecedor, model=d.modelo, role=d.papel, capabilities=[],
              permission_profile="so-leitura")
    s.add(a)
    await auditar(s, u.user.username, "agente-criado", agente=a.name)
    await s.commit()
    return _a(a)


@r.delete("/agents/{ident}")
async def apagar(ident: str, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    a = await s.get(Agent, ident)
    if not a:
        raise HTTPException(404, "Agente não encontrado.")
    usado = await s.scalar(select(func.count()).select_from(TeamTask).where(TeamTask.coordinator_id == a.id)) or \
        await s.scalar(select(func.count()).select_from(CollabTask).where(
            (CollabTask.first_agent_id == a.id) | (CollabTask.second_agent_id == a.id)))
    if usado:
        raise HTTPException(409, "Este agente aparece em tarefas antigas; desactive-o em vez de o apagar.")
    await s.delete(a)
    await auditar(s, u.user.username, "agente-apagado", agente=a.name)
    await s.commit()
    return {"ok": True}


@r.patch("/agents/{ident}")
async def mudar(ident: str, d: MudarAgente, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    a = await s.get(Agent, ident)
    if not a:
        raise HTTPException(404, "Agente não encontrado.")
    if d.perfil is not None and d.perfil not in agentes.PERFIS:
        raise HTTPException(400, "Só o perfil «so-leitura» está disponível nesta versão.")
    if d.modelo is not None:
        a.model = d.modelo
    if d.papel is not None:
        a.role = d.papel
    if d.activo is not None:
        a.enabled = d.activo
    if d.perfil is not None:
        a.permission_profile = d.perfil
    await auditar(s, u.user.username, "agente-alterado", agente=a.name)
    await s.commit()
    return _a(a)


@r.post("/agents/{ident}/run")
async def executar(ident: str, d: Pedido, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    a = await s.get(Agent, ident)
    if not a or not a.enabled:
        raise HTTPException(404, "Agente inexistente ou desactivado.")
    await _projecto_valido(s, d.projecto_id)
    await auditar(s, u.user.username, "agente-executado", agente=a.name)
    await s.commit()
    agentes.em_fundo(agentes.correr(a.id, d.pedido, d.projecto_id))
    return {"ok": True}


@r.get("/agents/{ident}/runs")
async def execucoes(ident: str, s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    q = select(AgentRun).where(AgentRun.agent_id == ident).order_by(AgentRun.id.desc()).limit(30)
    return [_run(x) for x in (await s.scalars(q)).all()]


@r.get("/collab")
async def colaboracoes(s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    q = select(CollabTask).order_by(CollabTask.created_at.desc()).limit(30)
    return [_t(t) for t in (await s.scalars(q)).all()]


@r.post("/collab")
async def colaborar(d: NovaColaboracao, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    for ident in (d.primeiro, d.segundo):
        a = await s.get(Agent, ident)
        if not a or not a.enabled:
            raise HTTPException(404, "Agente inexistente ou desactivado.")
    await _projecto_valido(s, d.projecto_id)
    t = CollabTask(prompt=d.pedido, project_id=d.projecto_id, first_agent_id=d.primeiro, second_agent_id=d.segundo)
    s.add(t)
    await auditar(s, u.user.username, "colaboracao-criada", tarefa=t.id)
    await s.commit()
    agentes.em_fundo(agentes.colaborar(t.id))
    return _t(t)


@r.get("/collab/{ident}")
async def ver(ident: str, s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    t = await s.get(CollabTask, ident)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    runs = (await s.scalars(select(AgentRun).where(AgentRun.task_id == t.id).order_by(AgentRun.id))).all()
    return _t(t, list(runs))


# --- Equipa ------------------------------------------------------------------------

class NovaEquipa(BaseModel):
    objectivo: str = Field(min_length=1, max_length=20000)
    coordenador: str
    membros: list[str] = Field(min_length=1, max_length=8)
    projecto_id: str | None = None
    rondas: int = Field(default=3, ge=1, le=6)
    conversation_id: str | None = Field(default=None, max_length=32)


class Nota(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)


class MemoriaPartilhada(BaseModel):
    texto: str = Field(default="", max_length=20000)


def _equipa(t: TeamTask, msgs: list[TeamMessage] | None = None) -> dict:
    d = {"id": t.id, "objectivo": t.goal, "projecto_id": t.project_id, "coordenador": t.coordinator_id,
         "membros": t.members, "conversation_id": t.conversation_id, "turno": t.turn_no,
         "rondas": t.max_rounds, "ronda": t.round, "estado": t.status, "resultado": t.result,
         "criada": t.created_at.isoformat() if t.created_at else None,
         "fim": t.finished_at.isoformat() if t.finished_at else None}
    if msgs is not None:
        d["quadro"] = [{"id": m.id, "ronda": m.round, "autor": m.author, "tipo": m.kind, "titulo": m.title,
                        "texto": m.content, "estado": m.status,
                        "quando": m.created_at.isoformat() if m.created_at else None} for m in msgs]
    return d


def _conversa(c: TeamConversation, actual: TeamTask | None = None) -> dict:
    return {"id": c.id, "titulo": c.title, "memoria": c.memory, "estado": c.status,
            "turnos": max(0, c.next_turn - 1),
            "actual": _equipa(actual) if actual else None,
            "criada": c.created_at.isoformat() if c.created_at else None,
            "actualizada": c.updated_at.isoformat() if c.updated_at else None}


@r.get("/team")
async def equipas(s: AsyncSession = Depends(sessao), _: Autenticado = Depends(autenticado)):
    q = select(TeamTask).order_by(TeamTask.created_at.desc()).limit(30)
    return [_equipa(t) for t in (await s.scalars(q)).all()]


@r.get("/team/conversations")
async def conversas_equipa(s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    q = (select(TeamConversation)
         .where((TeamConversation.owner_id == u.user.id) | TeamConversation.owner_id.is_(None))
         .order_by(TeamConversation.updated_at.desc()).limit(50))
    conversas = (await s.scalars(q)).all()
    saida = []
    for c in conversas:
        atual = await s.scalar(select(TeamTask).where(TeamTask.conversation_id == c.id)
                               .order_by(TeamTask.turn_no.desc(), TeamTask.created_at.desc()).limit(1))
        saida.append(_conversa(c, atual))
    return saida


@r.get("/team/conversations/{ident}")
async def ver_conversa_equipa(ident: str, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    c = await s.get(TeamConversation, ident)
    if not c or c.owner_id not in (None, u.user.id):
        raise HTTPException(404, "Conversa não encontrada.")
    tasks = (await s.scalars(select(TeamTask).where(TeamTask.conversation_id == c.id)
                             .order_by(TeamTask.turn_no, TeamTask.created_at, TeamTask.id))).all()
    ids = [t.id for t in tasks]
    msgs = (await s.scalars(select(TeamMessage).where(TeamMessage.task_id.in_(ids))
                            .order_by(TeamMessage.id))).all() if ids else []
    por_tarefa: dict[str, list[TeamMessage]] = {}
    for m in msgs:
        por_tarefa.setdefault(m.task_id, []).append(m)
    actual = tasks[-1] if tasks else None
    return {**_conversa(c, actual), "tarefas": [_equipa(t, por_tarefa.get(t.id, [])) for t in tasks]}


@r.patch("/team/conversations/{ident}/memory")
async def guardar_memoria(ident: str, d: MemoriaPartilhada, s: AsyncSession = Depends(sessao),
                          u: Autenticado = Depends(autenticado)):
    c = await s.get(TeamConversation, ident)
    if not c or c.owner_id not in (None, u.user.id):
        raise HTTPException(404, "Conversa não encontrada.")
    c.memory = d.texto.strip()
    c.updated_at = agora()
    await s.commit()
    return {"ok": True, "memoria": c.memory}


@r.post("/team")
async def nova_equipa(d: NovaEquipa, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    for ident in {d.coordenador, *d.membros}:
        a = await s.get(Agent, ident)
        if not a or not a.enabled:
            raise HTTPException(404, "Agente inexistente ou desactivado.")
    await _projecto_valido(s, d.projecto_id)
    if d.conversation_id:
        conversa = await s.get(TeamConversation, d.conversation_id)
        if not conversa or conversa.owner_id not in (None, u.user.id):
            raise HTTPException(404, "Conversa não encontrada.")
        turno = conversa.next_turn
        reserva = await s.execute(update(TeamConversation)
                                  .where(TeamConversation.id == conversa.id,
                                         TeamConversation.status == "activa",
                                         TeamConversation.next_turn == turno)
                                  .values(status="a-correr", next_turn=turno + 1, updated_at=agora()))
        if reserva.rowcount != 1:
            raise HTTPException(409, "A conversa já tem um turno em execução; aguarda ou envia uma nota.")
    else:
        conversa = TeamConversation(owner_id=u.user.id, title=d.objectivo.strip()[:160] or "Nova conversa",
                                    status="a-correr", next_turn=2)
        s.add(conversa)
        await s.flush()
        turno = 1
    t = TeamTask(goal=d.objectivo, project_id=d.projecto_id, coordinator_id=d.coordenador,
                 conversation_id=conversa.id, turn_no=turno, members=list(dict.fromkeys(d.membros)),
                 max_rounds=d.rondas, round=0, status="pendente", result="")
    s.add(t)
    await s.flush()
    s.add(TeamMessage(task_id=t.id, round=0, author=u.user.username, kind="pedido", title="Pedido do utilizador",
                      content=d.objectivo, status="feito"))
    await auditar(s, u.user.username, "equipa-criada", tarefa=t.id)
    await s.commit()
    agentes.em_fundo(equipa.correr_equipa(t.id))
    return _equipa(t)


@r.get("/team/{ident}")
async def ver_equipa(ident: str, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    t = await s.get(TeamTask, ident)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    await _verificar_dono_conversa(s, t, u)
    msgs = (await s.scalars(select(TeamMessage).where(TeamMessage.task_id == t.id).order_by(TeamMessage.id))).all()
    return _equipa(t, list(msgs))


@r.post("/team/{ident}/note")
async def nota(ident: str, d: Nota, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    t = await s.get(TeamTask, ident)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    await _verificar_dono_conversa(s, t, u)
    s.add(TeamMessage(task_id=t.id, round=t.round, author=u.user.username, kind="nota", title="Nota",
                      content=d.texto, status="feito"))
    await s.commit()
    return {"ok": True}


@r.post("/team/{ident}/stop")
async def parar_equipa(ident: str, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    t = await s.get(TeamTask, ident)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    await _verificar_dono_conversa(s, t, u)
    if t.status in ("pendente", "a-correr"):
        equipa.parar(t.id)
        await auditar(s, u.user.username, "equipa-parada", tarefa=t.id)
        await s.commit()
    return {"ok": True}


@r.post("/team/{ident}/retry")
async def repetir_equipa(ident: str, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    """Repete desde o plano uma equipa que terminou com erro ou foi interrompida."""
    t = await s.get(TeamTask, ident)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    if t.status not in ("erro", "parada"):
        raise HTTPException(409, "Só é possível repetir uma tarefa falhada ou interrompida.")
    if t.conversation_id:
        conversa = await s.get(TeamConversation, t.conversation_id)
        if not conversa or conversa.owner_id not in (None, u.user.id):
            raise HTTPException(404, "Conversa não encontrada.")
        reserva = await s.execute(update(TeamConversation).where(
            TeamConversation.id == conversa.id, TeamConversation.status == "activa"
        ).values(status="a-correr", updated_at=agora()))
        if reserva.rowcount != 1:
            raise HTTPException(409, "A conversa já tem um turno em execução.")
    t.status, t.result, t.finished_at = "pendente", "", None
    await auditar(s, u.user.username, "equipa-repetida", tarefa=t.id)
    await s.commit()
    agentes.em_fundo(equipa.correr_equipa(t.id))
    return _equipa(t)


class DoClaude(BaseModel):
    texto: str = Field(min_length=1, max_length=200_000)
    continuar: bool = True


@r.get("/team/{ident}/brief")
async def briefing(ident: str, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    t = await s.get(TeamTask, ident)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    await _verificar_dono_conversa(s, t, u)
    msgs = (await s.scalars(select(TeamMessage).where(TeamMessage.task_id == t.id).order_by(TeamMessage.id))).all()
    return {"texto": equipa.briefing(t.goal, list(msgs), t.result)}


@r.post("/team/{ident}/claude")
async def do_claude(ident: str, d: DoClaude, s: AsyncSession = Depends(sessao), u: Autenticado = Depends(autenticado)):
    """Resposta do Claude colada pelo utilizador. Se a tarefa já terminou e continuar=True,
    o coordenador retoma: revê o contributo e conclui ou pede mais (até 2 rondas extra)."""
    t = await s.get(TeamTask, ident)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada.")
    await _verificar_dono_conversa(s, t, u)
    s.add(TeamMessage(task_id=t.id, round=t.round, author="Claude", kind="claude",
                      title="Contributo do Claude (colado pelo utilizador)", content=d.texto, status="feito"))
    retomar = d.continuar and t.status not in ("pendente", "a-correr")
    if retomar:
        if t.conversation_id:
            reserva = await s.execute(update(TeamConversation).where(
                TeamConversation.id == t.conversation_id, TeamConversation.status == "activa"
            ).values(status="a-correr", updated_at=agora()))
            if reserva.rowcount != 1:
                raise HTTPException(409, "A conversa já tem um turno em execução.")
        t.status = "a-correr"
    await auditar(s, u.user.username, "equipa-claude", tarefa=t.id, retomar=retomar)
    await s.commit()
    if retomar:
        agentes.em_fundo(equipa.correr_equipa(t.id, retomar=True))
    return {"ok": True, "retomada": retomar}
