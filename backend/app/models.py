"""
Modelos de dados (SQLAlchemy 2). Nenhuma tabela guarda segredos de
fornecedores: as credenciais do Codex vivem em agents/codex (CODEX_HOME),
fora da base de dados.

Created by Redfox using Claude
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def novo_id() -> str:
    return uuid.uuid4().hex


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor: Mapped[str] = mapped_column(String(80))          # utilizador ou agente
    action: Mapped[str] = mapped_column(String(80), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # nunca segredos


# --- Fase 2: utilizadores e sessões de login ----------------------------------

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoginSession(Base):
    """Sessão do Command Centre (cookie). Guarda-se só o hash do token."""
    __tablename__ = "login_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str] = mapped_column(String(200), default="")


class LoginAttempt(Base):
    """Tentativas falhadas, para limitar a força bruta (por IP e por utilizador)."""
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


# --- Fase 3: projectos, sessões de conversa e mensagens -------------------------

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=novo_id)
    name: Mapped[str] = mapped_column(String(120))
    instructions: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatSession(Base):
    """Uma conversa: fornecedor, modelo, projecto, estado e as suas mensagens."""
    __tablename__ = "chat_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=novo_id)
    title: Mapped[str] = mapped_column(String(200), default="Nova conversa")
    provider: Mapped[str] = mapped_column(String(32))          # ollama | codex | claude-externo
    model: Mapped[str] = mapped_column(String(120))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"),
                                                   nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="activa")   # activa | arquivada | externa
    #: Identificador do lado do fornecedor (ex.: thread do Codex), para retomar.
    external_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    messages: Mapped[list[Message]] = relationship(back_populates="session", order_by="Message.id",
                                                   cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))              # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    session: Mapped[ChatSession] = relationship(back_populates="messages")


# --- Fase 5: documentos, memória, agentes, colaboração e aprovações --------------

class ProjectDocument(Base):
    __tablename__ = "project_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(400))
    size: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")        # texto extraído, para pesquisa e contexto
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemoryItem(Base):
    """Memória de projecto. O que um agente propõe fica pendente até o utilizador aprovar."""
    __tablename__ = "memory_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))             # nota | resumo | documento
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(80), default="utilizador")
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=novo_id)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(120))
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    #: so-leitura (omissão) | escrita-com-aprovacao
    permission_profile: Mapped[str] = mapped_column(String(32), default="so-leitura")
    #: Papel na equipa (o coordenador usa isto para distribuir trabalho).
    role: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(Base):
    """Histórico de execuções de um agente (incluindo cada passo de uma colaboração)."""
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), default="execucao")   # analise | revisao | consolidacao
    status: Mapped[str] = mapped_column(String(20), default="a-correr")  # a-correr | concluida | erro
    output: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CollabTask(Base):
    __tablename__ = "collab_tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=novo_id)
    prompt: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    first_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    second_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    status: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente | a-correr | concluida | erro
    result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Approval(Base):
    """
    Pedido de aprovação para qualquer acção que altere ficheiros, execute
    comandos, instale software ou mude configuração. Nenhum agente o contorna:
    o executor só corre o que estiver «aprovada».
    """
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=novo_id)
    source: Mapped[str] = mapped_column(String(80))           # agente / fornecedor
    kind: Mapped[str] = mapped_column(String(32))             # comando | ficheiro | instalacao | configuracao | permissoes
    summary: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pendente", index=True)
    # pendente | aprovada | rejeitada | executada | falhou | expirada
    result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


# --- Conversas persistentes e colaboração de equipa ------------------------------

class TeamConversation(Base):
    """Fio contínuo da equipa; transcrição e memória pertencem só a esta conversa."""
    __tablename__ = "team_conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=novo_id)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"),
                                                nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160), default="Nova conversa")
    memory: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="activa")  # activa | a-correr | arquivada
    next_turn: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


# --- Equipa: vários agentes coordenados num objectivo comum ---------------------

class TeamTask(Base):
    """Objectivo entregue a uma equipa; o coordenador divide, distribui e revê."""
    __tablename__ = "team_tasks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=novo_id)
    goal: Mapped[str] = mapped_column(Text)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    coordinator_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("team_conversations.id", ondelete="SET NULL"), nullable=True, index=True)
    turn_no: Mapped[int] = mapped_column(Integer, default=1)
    members: Mapped[list] = mapped_column(JSON, default=list)          # ids de agentes
    max_rounds: Mapped[int] = mapped_column(Integer, default=3)
    round: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente|a-correr|concluida|erro|parada
    result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TeamMessage(Base):
    """Quadro partilhado da equipa: planos, resultados, revisões e notas do utilizador."""
    __tablename__ = "team_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("team_tasks.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(Integer, default=0)
    author: Mapped[str] = mapped_column(String(80))      # nome do agente | utilizador | sistema
    kind: Mapped[str] = mapped_column(String(20))        # plano|subtarefa|resultado|revisao|final|nota|erro
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="feito")  # a-correr|feito|erro (subtarefas)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
