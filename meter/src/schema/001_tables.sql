-- =============================================================================
-- SCHEMA AND TABLES FOR POSTKIT/METER
-- =============================================================================
-- Double-entry ledger for usage tracking.
-- Meter measures. It does not price.
--
-- Design principles:
--   1. Double-entry ledger: Every balance change is an immutable ledger entry
--   2. Atomic operations: Check-and-decrement in single statement
--   3. Reservations: Hold tokens before operation, commit actual after
--   4. Idempotent: Safe retries via idempotency_key
--   5. Immutable audit trail: Ledger entries cannot be modified

CREATE SCHEMA IF NOT EXISTS meter;

-- =============================================================================
-- ACCOUNTS TABLE
-- =============================================================================
-- Current state, denormalized for fast reads.
-- One row per user/event_type/resource/unit combination.
-- Balance is authoritative but must equal SUM(ledger.amount) always.

CREATE TABLE meter.accounts (
    namespace text NOT NULL DEFAULT 'default',
    user_id text,                       -- NULL = namespace-level pool
    event_type text NOT NULL,
    resource text NOT NULL DEFAULT '',
    unit text NOT NULL,

    -- Current state
    balance numeric NOT NULL DEFAULT 0,
    reserved numeric NOT NULL DEFAULT 0,  -- amount held by active reservations

    -- Lifetime totals (for analytics)
    total_credited numeric NOT NULL DEFAULT 0,  -- sum of positive entries
    total_debited numeric NOT NULL DEFAULT 0,   -- sum of negative entries (stored positive)

    -- Period management
    period_start date,
    period_allocation numeric,          -- amount granted this period
    carry_over_limit numeric,           -- max unused to roll forward (NULL = no limit)

    -- Reconciliation
    last_entry_id bigint,
    last_reconciled_at timestamptz,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (namespace, user_id, event_type, resource, unit),

    CONSTRAINT accounts_balance_reserved CHECK (reserved >= 0),
    CONSTRAINT accounts_totals_positive CHECK (total_credited >= 0 AND total_debited >= 0)
);

-- Handle NULL user_id in primary key (namespace-level accounts)
CREATE UNIQUE INDEX accounts_namespace_pool_idx
    ON meter.accounts (namespace, event_type, resource, unit)
    WHERE user_id IS NULL;

-- =============================================================================
-- LEDGER TABLE
-- =============================================================================
-- Append-only, immutable. Every balance change is recorded here.
-- Partitioned by event_time for efficient retention management.
--
-- Entry types:
--   allocation          (+) Quota granted (purchase, plan, top-up)
--   consumption         (-) Usage recorded
--   reservation         (-) Hold for pending operation
--   reservation_release (+) Release unused hold
--   adjustment          (+/-) Correction (references original)
--   expiration          (-) Unused quota expired at period end
--   carry_over          (+) Rolled from previous period

CREATE TABLE meter.ledger (
    id bigint GENERATED ALWAYS AS IDENTITY,
    namespace text NOT NULL DEFAULT 'default',

    -- Account reference
    user_id text,
    event_type text NOT NULL,
    resource text NOT NULL DEFAULT '',
    unit text NOT NULL,

    -- Entry details
    entry_type text NOT NULL,
    amount numeric NOT NULL,            -- signed: + credit, - debit
    balance_after numeric NOT NULL,     -- running balance after this entry

    -- Timing
    event_time timestamptz NOT NULL,    -- when usage occurred
    created_at timestamptz NOT NULL DEFAULT now(),

    -- Idempotency
    idempotency_key text,

    -- For reservations
    reservation_id text,                -- groups reservation/release/commit
    expires_at timestamptz,             -- when reservation auto-expires

    -- For adjustments: reference to original entry
    reference_id bigint,

    -- Actor context
    actor_id text,
    on_behalf_of text,
    reason text,
    request_id text,

    metadata jsonb,

    PRIMARY KEY (id, event_time),

    CONSTRAINT ledger_entry_type_valid CHECK (entry_type IN (
        'allocation',
        'consumption',
        'reservation',
        'reservation_release',
        'adjustment',
        'expiration',
        'carry_over'
    )),
    CONSTRAINT ledger_amount_sign CHECK (
        (entry_type = 'allocation' AND amount > 0) OR
        (entry_type = 'consumption' AND amount < 0) OR
        (entry_type = 'reservation' AND amount < 0) OR
        (entry_type = 'reservation_release' AND amount > 0) OR
        (entry_type = 'expiration' AND amount < 0) OR
        (entry_type = 'carry_over' AND amount > 0) OR
        (entry_type = 'adjustment')
    ),
    CONSTRAINT ledger_reservation_fields CHECK (
        (entry_type IN ('reservation', 'reservation_release') AND reservation_id IS NOT NULL) OR
        (entry_type NOT IN ('reservation', 'reservation_release'))
    )
) PARTITION BY RANGE (event_time);

-- =============================================================================
-- RESERVATIONS TABLE
-- =============================================================================
-- Tracks pending reservations for expiry management.
-- Deleted when committed or released.

CREATE TABLE meter.reservations (
    reservation_id text PRIMARY KEY,
    namespace text NOT NULL,
    user_id text,
    event_type text NOT NULL,
    resource text NOT NULL DEFAULT '',
    unit text NOT NULL,

    amount numeric NOT NULL,
    ledger_id bigint NOT NULL,
    ledger_event_time timestamptz NOT NULL,

    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    actor_id text,
    request_id text,
    metadata jsonb
);

-- =============================================================================
-- ROW-LEVEL SECURITY
-- =============================================================================

ALTER TABLE meter.accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE meter.accounts FORCE ROW LEVEL SECURITY;
CREATE POLICY accounts_tenant_isolation ON meter.accounts
    USING (namespace = current_setting('meter.tenant_id', TRUE))
    WITH CHECK (namespace = current_setting('meter.tenant_id', TRUE));

ALTER TABLE meter.ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE meter.ledger FORCE ROW LEVEL SECURITY;
CREATE POLICY ledger_tenant_isolation ON meter.ledger
    USING (namespace = current_setting('meter.tenant_id', TRUE))
    WITH CHECK (namespace = current_setting('meter.tenant_id', TRUE));

ALTER TABLE meter.reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE meter.reservations FORCE ROW LEVEL SECURITY;
CREATE POLICY reservations_tenant_isolation ON meter.reservations
    USING (namespace = current_setting('meter.tenant_id', TRUE))
    WITH CHECK (namespace = current_setting('meter.tenant_id', TRUE));
