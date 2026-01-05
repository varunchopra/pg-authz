"""Core SDK tests for postkit.meter - happy path and basic functionality."""

from datetime import datetime, timedelta, timezone


class TestAllocate:
    """Tests for meter.allocate()"""

    def test_allocate_creates_account_and_balance(self, meter):
        """Allocating to a new user creates an account with that balance."""
        result = meter.allocate("user-1", "llm_call", 1000, "tokens")

        assert result["balance"] == 1000
        assert result["entry_id"] is not None

        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert balance["balance"] == 1000
        assert balance["reserved"] == 0
        assert balance["available"] == 1000

    def test_allocate_with_resource(self, meter):
        """Allocation with resource creates separate account."""
        meter.allocate("user-1", "llm_call", 1000, "tokens", resource="claude-sonnet")
        meter.allocate("user-1", "llm_call", 500, "tokens", resource="gpt-4")

        sonnet = meter.get_balance("user-1", "llm_call", "tokens", "claude-sonnet")
        gpt4 = meter.get_balance("user-1", "llm_call", "tokens", "gpt-4")

        assert sonnet["balance"] == 1000
        assert gpt4["balance"] == 500

    def test_allocate_idempotency(self, meter):
        """Duplicate idempotency key returns existing result."""
        result1 = meter.allocate(
            "user-1", "llm_call", 1000, "tokens", idempotency_key="alloc-1"
        )
        result2 = meter.allocate(
            "user-1", "llm_call", 1000, "tokens", idempotency_key="alloc-1"
        )

        assert result1["entry_id"] == result2["entry_id"]
        assert result1["balance"] == result2["balance"]

        # Balance should only be 1000, not 2000
        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert balance["balance"] == 1000

    def test_allocate_multiple_adds_up(self, meter):
        """Multiple allocations to same account add up."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        meter.allocate("user-1", "llm_call", 500, "tokens")

        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert balance["balance"] == 1500


class TestConsume:
    """Tests for meter.consume()"""

    def test_consume_deducts_from_balance(self, meter):
        """Consumption reduces balance."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        result = meter.consume("user-1", "llm_call", 100, "tokens")

        assert result["success"] is True
        assert result["balance"] == 900

    def test_consume_without_balance_check_allows_negative(self, meter):
        """Without check_balance, consumption can go negative."""
        meter.allocate("user-1", "llm_call", 100, "tokens")
        result = meter.consume("user-1", "llm_call", 200, "tokens")

        assert result["success"] is True
        assert result["balance"] == -100

    def test_consume_with_balance_check_fails_if_insufficient(self, meter):
        """With check_balance=True, consumption fails if insufficient."""
        meter.allocate("user-1", "llm_call", 100, "tokens")
        result = meter.consume("user-1", "llm_call", 200, "tokens", check_balance=True)

        assert result["success"] is False
        assert result["entry_id"] is None

        # Balance unchanged
        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert balance["balance"] == 100

    def test_consume_idempotency(self, meter):
        """Duplicate idempotency key returns existing result."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")

        result1 = meter.consume(
            "user-1", "llm_call", 100, "tokens", idempotency_key="consume-1"
        )
        result2 = meter.consume(
            "user-1", "llm_call", 100, "tokens", idempotency_key="consume-1"
        )

        assert result1["entry_id"] == result2["entry_id"]

        # Balance should only be reduced once
        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert balance["balance"] == 900

    def test_consume_returns_correct_available(self, meter):
        """Consume returns the new available balance matching get_balance."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        result = meter.consume("user-1", "llm_call", 100, "tokens")

        assert result["success"] is True
        assert result["balance"] == 900
        assert result["available"] == 900  # Must be NEW available, not old

        # Returned available must match get_balance
        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert result["available"] == balance["available"]

    def test_consume_available_with_reservation(self, meter):
        """Consume returns correct available when reservations exist."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        meter.reserve("user-1", "llm_call", 200, "tokens")  # reserved=200

        result = meter.consume("user-1", "llm_call", 100, "tokens")

        # After reserve: balance=800, reserved=200, available=600
        # After consume 100: balance=700, reserved=200, available=500
        assert result["balance"] == 700
        assert result["available"] == 500

        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert result["available"] == balance["available"]


class TestReservation:
    """Tests for meter.reserve(), meter.commit(), meter.release()"""

    def test_reserve_holds_balance(self, meter):
        """Reservation reduces available but keeps reserved tracked."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        result = meter.reserve("user-1", "llm_call", 400, "tokens")

        assert result["granted"] is True
        assert result["reservation_id"] is not None
        assert result["balance"] == 600  # balance reduced by reservation

        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert balance["balance"] == 600
        assert balance["reserved"] == 400
        assert balance["available"] == 200

    def test_reserve_returns_correct_available(self, meter):
        """Reserve returns the new available balance matching get_balance."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        result = meter.reserve("user-1", "llm_call", 400, "tokens")

        assert result["granted"] is True
        assert result["balance"] == 600
        assert result["available"] == 200  # Must match stored state

        # Returned available must match get_balance
        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert result["available"] == balance["available"]

    def test_reserve_available_with_existing_reservation(self, meter):
        """Reserve returns correct available when prior reservations exist."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")

        # First reservation
        res1 = meter.reserve("user-1", "llm_call", 300, "tokens")
        # After: balance=700, reserved=300, available=400
        assert res1["available"] == 400

        # Second reservation
        res2 = meter.reserve("user-1", "llm_call", 200, "tokens")
        # After: balance=500, reserved=500, available=0
        assert res2["balance"] == 500
        assert res2["available"] == 0

        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert res2["available"] == balance["available"]

    def test_reserve_fails_if_insufficient(self, meter):
        """Reservation fails if available balance is insufficient."""
        meter.allocate("user-1", "llm_call", 100, "tokens")
        result = meter.reserve("user-1", "llm_call", 200, "tokens")

        assert result["granted"] is False
        assert result["reservation_id"] is None

    def test_commit_with_exact_amount(self, meter):
        """Committing with exact reserved amount works correctly."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        res = meter.reserve("user-1", "llm_call", 400, "tokens")

        result = meter.commit(res["reservation_id"], 400)

        assert result["success"] is True
        assert result["consumed"] == 400
        assert result["released"] == 0
        assert result["reserved_amount"] == 400
        assert result["balance"] == 600

    def test_commit_with_less_than_reserved(self, meter):
        """Committing with less than reserved releases the difference."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        res = meter.reserve("user-1", "llm_call", 400, "tokens")

        result = meter.commit(res["reservation_id"], 250)

        assert result["success"] is True
        assert result["consumed"] == 250
        assert result["released"] == 150
        assert result["reserved_amount"] == 400
        assert result["balance"] == 750  # 1000 - 250

    def test_release_restores_balance(self, meter):
        """Releasing a reservation restores the balance."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        res = meter.reserve("user-1", "llm_call", 400, "tokens")

        result = meter.release(res["reservation_id"])

        assert result is True

        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert balance["balance"] == 1000
        assert balance["reserved"] == 0

    def test_release_nonexistent_returns_false(self, meter):
        """Releasing nonexistent reservation returns False."""
        result = meter.release("nonexistent-id")
        assert result is False

    def test_commit_nonexistent_returns_failure(self, meter):
        """Committing nonexistent reservation returns failure."""
        result = meter.commit("nonexistent-id", 100)
        assert result["success"] is False


class TestCommitOverage:
    """Tests for overage reporting in meter.commit()"""

    def test_commit_returns_reserved_amount(self, meter):
        """Commit returns the original reservation amount."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        res = meter.reserve("user-1", "llm_call", 400, "tokens")

        result = meter.commit(res["reservation_id"], 350)

        assert result["reserved_amount"] == 400
        assert result["consumed"] == 350
        assert result["released"] == 50

    def test_commit_overage_allowed_and_reported(self, meter):
        """Overage is allowed and accurately reported."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        res = meter.reserve("user-1", "llm_call", 400, "tokens")

        result = meter.commit(res["reservation_id"], 500)

        assert result["success"] is True
        assert result["reserved_amount"] == 400
        assert result["consumed"] == 500
        assert result["released"] == 0

        # Caller computes overage
        overage = max(0, result["consumed"] - result["reserved_amount"])
        assert overage == 100

    def test_commit_overage_can_go_negative(self, meter):
        """Overage can drive balance negative."""
        meter.allocate("user-1", "llm_call", 100, "tokens")
        res = meter.reserve("user-1", "llm_call", 100, "tokens")

        result = meter.commit(res["reservation_id"], 150)

        assert result["success"] is True
        assert result["balance"] == -50
        assert result["reserved_amount"] == 100
        assert result["consumed"] == 150


class TestAdjust:
    """Tests for meter.adjust()"""

    def test_adjust_positive_credits_account(self, meter):
        """Positive adjustment adds to balance."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        result = meter.adjust("user-1", "llm_call", 500, "tokens")

        assert result["balance"] == 1500

    def test_adjust_negative_debits_account(self, meter):
        """Negative adjustment subtracts from balance."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        result = meter.adjust("user-1", "llm_call", -200, "tokens")

        assert result["balance"] == 800

    def test_adjust_idempotency(self, meter):
        """Duplicate idempotency key returns existing result."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")

        result1 = meter.adjust(
            "user-1", "llm_call", 500, "tokens", idempotency_key="adj-1"
        )
        result2 = meter.adjust(
            "user-1", "llm_call", 500, "tokens", idempotency_key="adj-1"
        )

        assert result1["entry_id"] == result2["entry_id"]

        balance = meter.get_balance("user-1", "llm_call", "tokens")
        assert balance["balance"] == 1500  # Only adjusted once


class TestQuery:
    """Tests for query functions"""

    def test_get_user_balances(self, meter):
        """get_user_balances returns all accounts for a user."""
        meter.allocate("user-1", "llm_call", 1000, "tokens", resource="claude-sonnet")
        meter.allocate("user-1", "llm_call", 500, "tokens", resource="gpt-4")
        meter.allocate("user-1", "api_call", 100, "requests")

        balances = meter.get_user_balances("user-1")

        assert len(balances) == 3

    def test_get_ledger(self, meter):
        """get_ledger returns ledger entries for an account."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        meter.consume("user-1", "llm_call", 100, "tokens")
        meter.consume("user-1", "llm_call", 200, "tokens")

        ledger = meter.get_ledger("user-1", "llm_call", "tokens")

        assert len(ledger) == 3
        assert ledger[0]["entry_type"] == "consumption"  # Most recent first
        assert ledger[1]["entry_type"] == "consumption"
        assert ledger[2]["entry_type"] == "allocation"

    def test_get_usage(self, meter):
        """get_usage aggregates consumption."""
        meter.allocate("user-1", "llm_call", 10000, "tokens")
        meter.consume("user-1", "llm_call", 100, "tokens")
        meter.consume("user-1", "llm_call", 200, "tokens")
        meter.consume("user-1", "llm_call", 300, "tokens")

        # Use timezone-aware datetimes for proper timestamptz comparison
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=1)
        end = now + timedelta(hours=1)

        usage = meter.get_usage("user-1", start, end)

        assert len(usage) == 1
        assert usage[0]["total_consumed"] == 600
        assert usage[0]["event_count"] == 3

    def test_get_balance_nonexistent_returns_zeros(self, meter):
        """get_balance for nonexistent account returns zeros."""
        balance = meter.get_balance("nonexistent", "llm_call", "tokens")

        assert balance["balance"] == 0
        assert balance["reserved"] == 0
        assert balance["available"] == 0


class TestStats:
    """Tests for stats and reconciliation"""

    def test_get_stats(self, meter):
        """get_stats returns namespace statistics."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        meter.allocate("user-2", "llm_call", 500, "tokens")

        stats = meter.get_stats()

        assert stats["total_accounts"] == 2
        assert stats["total_ledger_entries"] == 2
        assert stats["total_balance"] == 1500

    def test_reconcile_no_discrepancies(self, meter, test_helpers):
        """reconcile returns empty when ledger matches accounts."""
        meter.allocate("user-1", "llm_call", 1000, "tokens")
        meter.consume("user-1", "llm_call", 300, "tokens")

        discrepancies = meter.reconcile()
        assert len(discrepancies) == 0

        # Verify helper agrees
        ledger_sum = test_helpers.sum_ledger_amounts("user-1", "llm_call", "tokens")
        account = test_helpers.get_account_raw("user-1", "llm_call", "tokens")
        assert ledger_sum == float(account["balance"])
