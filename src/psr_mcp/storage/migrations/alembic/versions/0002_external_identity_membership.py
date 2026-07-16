"""Add tenant-scoped OAuth external identity mappings."""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0002_external_identity"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = (Path(__file__).parents[2] / "0002_external_identity_membership.sql").read_text(
        encoding="utf-8"
    )
    sql = sql.removeprefix("BEGIN;").strip()
    if not sql.endswith("COMMIT;"):
        raise RuntimeError("external identity SQL must end with COMMIT")
    op.get_bind().exec_driver_sql(sql.removesuffix("COMMIT;").strip())


def downgrade() -> None:
    sql = (Path(__file__).parents[2] / "0002_external_identity_membership.down.sql").read_text(
        encoding="utf-8"
    )
    op.get_bind().exec_driver_sql(sql)
