"""signature versioning

Revision ID: 6a57edb25d31
Revises: 5bb952a2a435
Create Date: 2026-07-08

Nota: se usa batch_alter_table porque SQLite no soporta ALTER de
constraints directo (necesita el patrón copy-and-move). En Postgres,
batch_alter_table simplemente ejecuta los ALTER normales, así que esta
migración funciona igual en ambos motores.
"""
from alembic import op
import sqlalchemy as sa

revision = '6a57edb25d31'
down_revision = '5bb952a2a435'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('signature_requests') as batch_op:
        batch_op.add_column(
            sa.Column('version', sa.Integer(), nullable=False, server_default='1')
        )
        batch_op.add_column(sa.Column('parent_signature_id', sa.String(), nullable=True))
        batch_op.create_foreign_key(
            'fk_signature_requests_parent', 'signature_requests',
            ['parent_signature_id'], ['id']
        )


def downgrade():
    with op.batch_alter_table('signature_requests') as batch_op:
        batch_op.drop_constraint('fk_signature_requests_parent', type_='foreignkey')
        batch_op.drop_column('parent_signature_id')
        batch_op.drop_column('version')
