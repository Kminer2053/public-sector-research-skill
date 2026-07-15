-- PSR MCP Foundation schema draft for PostgreSQL 16+.
-- Application supplies UUID values. Runtime role must not own tables or have BYPASSRLS.

BEGIN;

CREATE TABLE organizations (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    status text NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED')),
    created_at timestamptz NOT NULL
);

CREATE TABLE users (
    id uuid PRIMARY KEY,
    external_subject text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL
);

CREATE TABLE memberships (
    organization_id uuid NOT NULL REFERENCES organizations(id),
    user_id uuid NOT NULL REFERENCES users(id),
    roles text[] NOT NULL CHECK (cardinality(roles) > 0),
    status text NOT NULL CHECK (status IN ('ACTIVE', 'REVOKED')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (organization_id, user_id)
);

CREATE TABLE projects (
    id uuid NOT NULL,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    profile text NOT NULL CHECK (char_length(profile) BETWEEN 1 AND 64),
    status text NOT NULL CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    version integer NOT NULL CHECK (version >= 1),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (organization_id, id)
);

CREATE TABLE membership_projects (
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    project_id uuid NOT NULL,
    PRIMARY KEY (organization_id, user_id, project_id),
    FOREIGN KEY (organization_id, user_id)
        REFERENCES memberships (organization_id, user_id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES projects (organization_id, id)
);

CREATE TABLE research_plans (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    version integer NOT NULL CHECK (version >= 1),
    question text NOT NULL CHECK (char_length(question) BETWEEN 1 AND 4000),
    status text NOT NULL CHECK (status IN ('DRAFT', 'IN_REVIEW', 'APPROVED', 'REJECTED')),
    approved_by uuid NULL REFERENCES users(id),
    approved_at timestamptz NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (organization_id, id, version),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES projects (organization_id, id),
    CHECK (
        (status = 'APPROVED' AND approved_by IS NOT NULL AND approved_at IS NOT NULL)
        OR
        (status <> 'APPROVED' AND approved_by IS NULL AND approved_at IS NULL)
    )
);

CREATE TABLE research_runs (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    plan_version integer NOT NULL,
    initiated_by uuid NOT NULL REFERENCES users(id),
    status text NOT NULL CHECK (
        status IN ('QUEUED', 'RUNNING', 'PARTIAL', 'SUCCEEDED', 'FAILED', 'CANCELLED')
    ),
    version integer NOT NULL CHECK (version >= 1),
    idempotency_key text NOT NULL CHECK (char_length(idempotency_key) BETWEEN 8 AND 128),
    request_fingerprint text NOT NULL CHECK (request_fingerprint ~ '^[a-f0-9]{64}$'),
    failure_code text NULL,
    cancel_reason text NULL,
    cancellation_requested_at timestamptz NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    started_at timestamptz NULL,
    finished_at timestamptz NULL,
    PRIMARY KEY (organization_id, id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES projects (organization_id, id),
    FOREIGN KEY (organization_id, plan_id, plan_version)
        REFERENCES research_plans (organization_id, id, version),
    UNIQUE (organization_id, project_id, initiated_by, idempotency_key)
);

CREATE TABLE jobs (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    run_id uuid NOT NULL,
    state text NOT NULL CHECK (
        state IN ('QUEUED', 'RUNNING', 'PARTIAL', 'SUCCEEDED', 'FAILED', 'CANCELLED')
    ),
    available_at timestamptz NOT NULL,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    lease_owner text NULL,
    lease_expires_at timestamptz NULL,
    cancel_requested_at timestamptz NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (organization_id, id),
    UNIQUE (organization_id, run_id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES projects (organization_id, id),
    FOREIGN KEY (organization_id, run_id)
        REFERENCES research_runs (organization_id, id),
    CHECK (
        (state = 'RUNNING' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (state <> 'RUNNING' AND lease_owner IS NULL AND lease_expires_at IS NULL)
    )
);

CREATE INDEX jobs_claim_idx
    ON jobs (organization_id, available_at, created_at, id)
    WHERE state IN ('QUEUED', 'RUNNING');

CREATE TABLE audit_events (
    id uuid NOT NULL,
    organization_id uuid NOT NULL REFERENCES organizations(id),
    project_id uuid NULL,
    occurred_at timestamptz NOT NULL,
    actor_subject_id text NOT NULL,
    actor_type text NOT NULL CHECK (actor_type IN ('human', 'service')),
    operation text NOT NULL,
    target_type text NOT NULL,
    target_id text NULL,
    outcome text NOT NULL CHECK (
        outcome IN ('SUCCEEDED', 'DENIED', 'FAILED', 'IDEMPOTENT_REPLAY')
    ),
    operation_id text NOT NULL,
    reason_code text NULL,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (organization_id, id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES projects (organization_id, id)
);

CREATE INDEX audit_events_operation_idx
    ON audit_events (organization_id, operation_id);

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships FORCE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
ALTER TABLE membership_projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE membership_projects FORCE ROW LEVEL SECURITY;
ALTER TABLE research_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_plans FORCE ROW LEVEL SECURITY;
ALTER TABLE research_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;

CREATE POLICY organizations_tenant_policy ON organizations
    USING (id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

CREATE POLICY memberships_tenant_policy ON memberships
    USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

CREATE POLICY projects_tenant_policy ON projects
    USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

CREATE POLICY membership_projects_tenant_policy ON membership_projects
    USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

CREATE POLICY research_plans_tenant_policy ON research_plans
    USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

CREATE POLICY research_runs_tenant_policy ON research_runs
    USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

CREATE POLICY jobs_tenant_policy ON jobs
    USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

CREATE POLICY audit_events_tenant_policy ON audit_events
    USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

CREATE FUNCTION prevent_audit_event_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_events are append-only';
END;
$$;

CREATE TRIGGER audit_events_no_update_or_delete
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();

COMMIT;
