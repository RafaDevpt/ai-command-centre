"""Conversas contínuas da Equipa com memória partilhada.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_conversations",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(160), nullable=False, server_default="Nova conversa"),
        sa.Column("memory", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="activa"),
        sa.Column("next_turn", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_team_conversations_owner_id", "team_conversations", ["owner_id"])
    op.create_index("ix_team_conversations_updated_at", "team_conversations", ["updated_at"])
    with op.batch_alter_table("team_tasks") as tarefas:
        tarefas.add_column(sa.Column(
            "conversation_id", sa.String(32),
            sa.ForeignKey("team_conversations.id", name="fk_team_tasks_conversation_id_team_conversations",
                          ondelete="SET NULL"), nullable=True))
        tarefas.add_column(sa.Column("turn_no", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_team_tasks_conversation_id", "team_tasks", ["conversation_id"])

    # Preserva o histórico existente: cada tarefa antiga passa a ser uma conversa
    # autónoma sem proprietário (visível na instalação pessoal já existente).
    conn = op.get_bind()
    tasks = sa.table(
        "team_tasks",
        sa.column("id", sa.String(32)),
        sa.column("goal", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("conversation_id", sa.String(32)),
        sa.column("turn_no", sa.Integer()),
    )
    conversations = sa.table(
        "team_conversations",
        sa.column("id", sa.String(32)),
        sa.column("title", sa.String(160)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("next_turn", sa.Integer()),
    )
    for row in conn.execute(sa.select(tasks.c.id, tasks.c.goal, tasks.c.created_at)):
        conn.execute(conversations.insert().values(
            id=row.id, title=(row.goal or "Conversa anterior")[:160],
            created_at=row.created_at, updated_at=row.created_at, next_turn=2))
        conn.execute(tasks.update().where(tasks.c.id == row.id).values(conversation_id=row.id, turn_no=1))


def downgrade() -> None:
    op.drop_index("ix_team_tasks_conversation_id", "team_tasks")
    with op.batch_alter_table("team_tasks") as tarefas:
        tarefas.drop_column("turn_no")
        tarefas.drop_column("conversation_id")
    op.drop_index("ix_team_conversations_updated_at", "team_conversations")
    op.drop_index("ix_team_conversations_owner_id", "team_conversations")
    op.drop_table("team_conversations")
