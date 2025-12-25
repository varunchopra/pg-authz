#!/bin/bash
# scripts/build.sh - Combine source SQL files into single distributable file

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$ROOT_DIR/src"

cat << 'HEADER'
-- pg-authz: Postgres-native authorization
-- https://github.com/varunchopra/pg-authz
--
-- Install: psql $DATABASE_URL -f pg-authz.sql
-- License: Apache 2.0
--
-- Generated file - do not edit directly. See src/ for source.

BEGIN;

HEADER

# Schema (ordered)
echo "-- ============================================"
echo "-- Schema"
echo "-- ============================================"
echo ""
for f in "$SRC_DIR"/schema/*.sql; do
    [ -f "$f" ] || continue
    echo "-- Source: schema/$(basename "$f")"
    cat "$f"
    echo ""
done

# Functions (ordered)
echo "-- ============================================"
echo "-- Functions"
echo "-- ============================================"
echo ""
for f in "$SRC_DIR"/functions/*.sql; do
    [ -f "$f" ] || continue
    echo "-- Source: functions/$(basename "$f")"
    cat "$f"
    echo ""
done

# Triggers (ordered)
echo "-- ============================================"
echo "-- Triggers"
echo "-- ============================================"
echo ""
for f in "$SRC_DIR"/triggers/*.sql; do
    [ -f "$f" ] || continue
    echo "-- Source: triggers/$(basename "$f")"
    cat "$f"
    echo ""
done

cat << 'FOOTER'

COMMIT;

-- ============================================
-- Installation complete
-- ============================================
--
-- Quick test:
--   SELECT authz.write('doc', '1', 'read', 'user', 'alice');
--   SELECT authz.check('alice', 'read', 'doc', '1');
--
FOOTER
