# Meter API Reference

## Python SDK

| Function | Description |
|----------|-------------|
| [`adjust`](sdk.md#adjust) | Create an adjustment entry (correction, refund, etc.). |
| [`allocate`](sdk.md#allocate) | Add quota/credits to an account. |
| [`clear_actor`](sdk.md#clear_actor) | Clear actor context. |
| [`close_period`](sdk.md#close_period) | Close a billing period, handle expiration and carry-over. |
| [`commit`](sdk.md#commit) | Commit a reservation with actual consumption. |
| [`consume`](sdk.md#consume) | Record consumption. |
| [`get_audit_events`](sdk.md#get_audit_events) | Query audit events with optional filters. |
| [`get_balance`](sdk.md#get_balance) | Get current balance for an account. |
| [`get_ledger`](sdk.md#get_ledger) | Get ledger entries for an account. |
| [`get_stats`](sdk.md#get_stats) | Get namespace statistics. |
| [`get_usage`](sdk.md#get_usage) | Get aggregated consumption for a user. |
| [`get_user_balances`](sdk.md#get_user_balances) | Get all balances for a user across all event types and resources. |
| [`open_period`](sdk.md#open_period) | Open a new billing period with allocation. |
| [`reconcile`](sdk.md#reconcile) | Check for discrepancies between accounts and ledger. |
| [`release`](sdk.md#release) | Release a reservation without consuming. |
| [`release_expired_reservations`](sdk.md#release_expired_reservations) | Release all expired reservations for this namespace. |
| [`reserve`](sdk.md#reserve) | Reserve quota for pending operation (streaming, uncertain consumption). |
| [`set_actor`](sdk.md#set_actor) | Set actor context for audit logging. |
| [`set_period_config`](sdk.md#set_period_config) | Configure period settings for an account. |

## SQL Functions

| Function | Description |
|----------|-------------|
| [`meter.create_partition`](sql.md#metercreate_partition) | Create a monthly partition for ledger |
| [`meter.drop_old_partitions`](sql.md#meterdrop_old_partitions) | Drop partitions older than retention period |
| [`meter.ensure_partitions`](sql.md#meterensure_partitions) | Create partitions for upcoming months |
| [`meter.get_stats`](sql.md#meterget_stats) | Get namespace statistics |
| [`meter.reconcile`](sql.md#meterreconcile) | Verify ledger sum matches account balance |
| [`meter.clear_actor`](sql.md#meterclear_actor) | Clear actor context |
| [`meter.clear_tenant`](sql.md#meterclear_tenant) | Clear tenant context |
| [`meter.set_actor`](sql.md#meterset_actor) | Set actor context for audit trail |
| [`meter.set_tenant`](sql.md#meterset_tenant) | Set the tenant context for Row-Level Security |
| [`meter.close_period`](sql.md#meterclose_period) | Close a billing period, handle expiration and carry-over |
| [`meter.open_period`](sql.md#meteropen_period) | Open a new billing period with fresh allocation |
| [`meter.release_expired_reservations`](sql.md#meterrelease_expired_reservations) | Release all expired reservations |
| [`meter.set_period_config`](sql.md#meterset_period_config) | Configure period settings for an account |
| [`meter.get_account`](sql.md#meterget_account) | Get full account details |
| [`meter.get_balance`](sql.md#meterget_balance) | Get current balance for an account |
| [`meter.get_ledger`](sql.md#meterget_ledger) | Get ledger entries for an account |
| [`meter.get_namespace_usage`](sql.md#meterget_namespace_usage) | Get org-level usage totals across all users |
| [`meter.get_usage`](sql.md#meterget_usage) | Get aggregated usage (consumption only) for a user |
| [`meter.get_user_balances`](sql.md#meterget_user_balances) | Get all balances for a user across all event types and resources |
| [`meter.adjust`](sql.md#meteradjust) | Create an adjustment entry (correction, refund, etc.) |
| [`meter.allocate`](sql.md#meterallocate) | Add quota/credits to an account |
| [`meter.commit`](sql.md#metercommit) | Commit a reservation with actual consumption. Returns reserved_amount so caller can compute overage. |
| [`meter.consume`](sql.md#meterconsume) | Record consumption (debit from account) |
| [`meter.release`](sql.md#meterrelease) | Release a reservation without consuming |
| [`meter.reserve`](sql.md#meterreserve) | Reserve quota for pending operation (streaming, uncertain consumption) |
