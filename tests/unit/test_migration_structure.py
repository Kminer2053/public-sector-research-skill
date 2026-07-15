from __future__ import annotations

from pathlib import Path


def test_foundation_migration_has_tenant_and_durability_guards() -> None:
    sql = Path("src/psr_mcp/storage/migrations/0001_foundation.sql").read_text()
    tenant_tables = [
        "memberships",
        "projects",
        "membership_projects",
        "research_plans",
        "research_runs",
        "jobs",
        "audit_events",
    ]
    for table in tenant_tables:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
    assert "FOR UPDATE SKIP LOCKED" not in sql  # claim belongs in repository query, not migration
    assert "UNIQUE (organization_id, project_id, initiated_by, idempotency_key)" in sql
    assert "prevent_audit_event_mutation" in sql
