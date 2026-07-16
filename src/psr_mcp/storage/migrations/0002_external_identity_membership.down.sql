DROP POLICY IF EXISTS external_identities_tenant_policy ON external_identities;
DROP TABLE IF EXISTS external_identities;
ALTER TABLE memberships DROP COLUMN IF EXISTS project_scope;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE external_subject IS NULL)
       OR EXISTS (
           SELECT external_subject
           FROM users
           GROUP BY external_subject
           HAVING count(*) > 1
       ) THEN
        RAISE EXCEPTION
            'cannot downgrade: users.external_subject no longer satisfies legacy uniqueness';
    END IF;
END;
$$;

ALTER TABLE users ALTER COLUMN external_subject SET NOT NULL;
ALTER TABLE users ADD CONSTRAINT users_external_subject_key UNIQUE (external_subject);
COMMENT ON COLUMN users.external_subject IS NULL;
