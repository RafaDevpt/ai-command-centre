"""Equipa: papel dos agentes, tarefas de equipa e quadro partilhado.

Created by Redfox using Claude

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("role", sa.Text(), nullable=False, server_default=""))
    op.create_table(
        "team_tasks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("coordinator_id", sa.String(32), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("members", sa.JSON(), nullable=False),
        sa.Column("max_rounds", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "team_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(32), sa.ForeignKey("team_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("author", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_team_messages_task_id", "team_messages", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_team_messages_task_id", "team_messages")
    op.drop_table("team_messages")
    op.drop_table("team_tasks")
    op.drop_column("agents", "role")
