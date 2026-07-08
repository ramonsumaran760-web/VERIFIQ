"""audit log inmutable a nivel de base de datos

Revision ID: 0002_audit_immutability
Revises: 185c82b95142
Create Date: 2026-07-07

Nota: la sintaxis de trigger aquí es SQLite (para dev). En Postgres el
equivalente real es una REVOKE UPDATE, DELETE ON audit_log FROM app_role,
más un trigger BEFORE UPDATE OR DELETE que haga RAISE EXCEPTION — se deja
comentado abajo porque depende del rol de conexión que se use en producción.
"""
from alembic import op

revision = "0002_audit_immutability"
down_revision = "185c82b95142"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS audit_log_no_update
            BEFORE UPDATE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log es append-only: UPDATE no permitido');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
            BEFORE DELETE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log es append-only: DELETE no permitido');
            END;
            """
        )
    elif bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION block_audit_log_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'audit_log es append-only: % no permitido', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_log_no_update
            BEFORE UPDATE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION block_audit_log_mutation();
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_log_no_delete
            BEFORE DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION block_audit_log_mutation();
            """
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_update;")
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete;")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_update ON audit_log;")
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete ON audit_log;")
        op.execute("DROP FUNCTION IF EXISTS block_audit_log_mutation;")
