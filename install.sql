-- postkit: Postgres-native authentication, authorization, and organizations
-- https://github.com/varunchopra/postkit
--
-- This file installs all postkit schemas. For individual modules, use:
--   authn/install.sql  - Authentication
--   authz/install.sql  - Authorization
--   orgs/install.sql   - Organizations
--
-- Usage:
--   psql $DATABASE_URL -f install.sql
--
-- Or use the pre-built distribution:
--   psql $DATABASE_URL -f dist/postkit.sql

\echo 'Installing postkit...'

-- Install each module
\ir authz/install.sql
-- \ir authn/install.sql  -- Coming soon
-- \ir orgs/install.sql   -- Coming soon

\echo 'postkit installation complete.'
\echo ''
\echo 'Quick test:'
\echo '  SELECT authz.write(''doc'', ''1'', ''read'', ''user'', ''alice'');'
\echo '  SELECT authz.check(''alice'', ''read'', ''doc'', ''1'');'
