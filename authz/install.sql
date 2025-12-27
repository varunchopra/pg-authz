-- postkit/authz: Relationship-Based Access Control (ReBAC)
-- https://github.com/varunchopra/postkit
--
-- This file installs only the authz schema. For all modules, use the root install.sql.
--
-- Usage:
--   psql $DATABASE_URL -f authz/install.sql
--
-- Or use the pre-built distribution:
--   psql $DATABASE_URL -f dist/authz.sql

\echo 'Installing authz schema...'

BEGIN;

-- Schema
\ir src/schema/001_tables.sql
\ir src/schema/002_indexes.sql
\ir src/schema/003_audit.sql
\ir src/schema/004_types.sql

-- Functions (in dependency order)
\ir src/functions/000_config.sql
\ir src/functions/001_validation.sql
\ir src/functions/010_helpers.sql
\ir src/functions/011_cycle_detection.sql
\ir src/functions/020_write.sql
\ir src/functions/021_delete.sql
\ir src/functions/022_check.sql
\ir src/functions/023_list.sql
\ir src/functions/024_explain.sql
\ir src/functions/030_hierarchy.sql
\ir src/functions/031_expiration.sql
\ir src/functions/032_maintenance.sql
\ir src/functions/033_audit.sql
\ir src/functions/034_rls.sql

-- Triggers
\ir src/triggers/002_audit.sql

COMMIT;

\echo 'authz installation complete.'
