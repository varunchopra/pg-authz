# Config API Reference

## Python SDK

| Function | Description |
|----------|-------------|
| [`activate`](sdk.md#activate) | Activate a specific version. |
| [`cleanup_old_versions`](sdk.md#cleanup_old_versions) | Delete old inactive versions, keeping N most recent per key. |
| [`clear_actor`](sdk.md#clear_actor) | Clear actor context. |
| [`delete`](sdk.md#delete) | Delete all versions of a config entry. |
| [`delete_version`](sdk.md#delete_version) | Delete a specific version (cannot delete active version). |
| [`exists`](sdk.md#exists) | Check if a config key exists. |
| [`get`](sdk.md#get) | Get config entry. |
| [`get_audit_events`](sdk.md#get_audit_events) | Query audit events. |
| [`get_batch`](sdk.md#get_batch) | Get multiple config entries in one query. |
| [`get_path`](sdk.md#get_path) | Get a specific path within a config value. |
| [`get_stats`](sdk.md#get_stats) | Get namespace statistics. |
| [`get_value`](sdk.md#get_value) | Get just the value (convenience method). |
| [`history`](sdk.md#history) | Get version history for a key. |
| [`list`](sdk.md#list) | List active config entries. |
| [`merge`](sdk.md#merge) | Merge changes into config, creating new version. |
| [`rollback`](sdk.md#rollback) | Rollback to previous version. |
| [`search`](sdk.md#search) | Find configs where value contains given JSON. |
| [`set`](sdk.md#set) | Create a new version and activate it. |
| [`set_actor`](sdk.md#set_actor) | Set actor context for audit logging. |

## SQL Functions

| Function | Description |
|----------|-------------|
| [`config.clear_actor`](sql.md#configclear_actor) | Clear actor context |
| [`config.create_audit_partition`](sql.md#configcreate_audit_partition) | Create a monthly partition for audit events |
| [`config.drop_audit_partitions`](sql.md#configdrop_audit_partitions) | Delete old audit partitions |
| [`config.ensure_audit_partitions`](sql.md#configensure_audit_partitions) | Create partitions for upcoming months |
| [`config.set_actor`](sql.md#configset_actor) | Set actor context for audit logging |
| [`config.activate`](sql.md#configactivate) | Activate a specific version (for rollback or promotion) |
| [`config.delete`](sql.md#configdelete) | Delete all versions of a config entry |
| [`config.delete_version`](sql.md#configdelete_version) | Delete a specific version (cannot delete active version) |
| [`config.exists`](sql.md#configexists) | Check if a config key exists (has an active version) |
| [`config.get`](sql.md#configget) | Get a config entry (active version or specific version) |
| [`config.get_batch`](sql.md#configget_batch) | Get multiple config entries in one query |
| [`config.get_path`](sql.md#configget_path) | Get a specific JSON path from active config |
| [`config.history`](sql.md#confighistory) | Get version history for a key |
| [`config.list`](sql.md#configlist) | List all active config entries |
| [`config.merge`](sql.md#configmerge) | Merge changes into config, creating new version |
| [`config.rollback`](sql.md#configrollback) | Activate the previous version |
| [`config.search`](sql.md#configsearch) | Find configs where value contains given JSON |
| [`config.set`](sql.md#configset) | Create a new version of a config entry and activate it |
| [`config.cleanup_old_versions`](sql.md#configcleanup_old_versions) | Delete old inactive versions, keeping N most recent per key |
| [`config.get_stats`](sql.md#configget_stats) | Get namespace statistics |
| [`config.clear_tenant`](sql.md#configclear_tenant) | Clear tenant context. Queries return no rows (fail-closed for safety). |
| [`config.set_tenant`](sql.md#configset_tenant) | Set the tenant context for Row-Level Security |
