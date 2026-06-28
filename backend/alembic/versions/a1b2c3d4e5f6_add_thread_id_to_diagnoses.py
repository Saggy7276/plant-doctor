"""add_thread_id_to_diagnoses

Revision ID: a1b2c3d4e5f6
Revises: 07e44fd61f16
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '07e44fd61f16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('diagnoses', sa.Column('thread_id', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('diagnoses', 'thread_id')
