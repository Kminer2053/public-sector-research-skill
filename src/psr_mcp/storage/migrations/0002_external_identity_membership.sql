-- Tenant-scoped external identity mappings for OAuth membership resolution.

BEGIN;

ALTER TABLE users DROP CONSTRAINT users_external_subject_key;
ALTER TABLE users ALTER COLUMN external_subject DROP NOT NULL;
COMMENT ON COLUMN users.external_subject IS
    'Deprecated legacy field. OAuth mappings live in tenant-scoped external_identities.';

ALTER TABLE memberships
    ADD COLUMN project_scope text NOT NULL DEFAULT 'ALL'
    CHECK (project_scope IN ('ALL', 'RESTRICTED'));

CREATE TABLE external_identities (
    organization_id uuid NOT NULL,
    user_id uuid NOT NULL,
    issuer text NOT NULL CHECK (char_length(issuer) BETWEEN 8 AND 2048),
    external_subject text NOT NULL CHECK (char_length(external_subject) BETWEEN 1 AND 512),
    actor_type text NOT NULL DEFAULT 'human' CHECK (actor_type IN ('human', 'service')),
    created_at timestamptz NOT NULL,
    PRIMARY KEY (organization_id, issuer, external_subject),
    UNIQUE (organization_id, user_id, issuer),
    FOREIGN KEY (organization_id, user_id)
        REFERENCES memberships (organization_id, user_id)
        ON DELETE CASCADE
);

ALTER TABLE external_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE external_identities FORCE ROW LEVEL SECURITY;

CREATE POLICY external_identities_tenant_policy ON external_identities
    USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);

COMMIT;
