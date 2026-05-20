# Decisions

## 2026-05-20: Initial scaffolding

### Context

I need a working, empty project skeleton before I build the first real Mercury ingest slice.

### Decision

I am creating the package, CLI, config loader, SQLite schema, setup command, logging, Telegram bot entrypoint, renderer stubs, scheduler stub, and install scripts exactly as specified.

### Alternatives

I considered waiting to add some files until they have real behavior, but that would make the next phase harder to verify.

### Why

I want every command, import, path, and setup step to work now, while keeping business logic out until the next phase.

## 2026-05-20: Slice 1: Mercury ingest

### Context

I need the first real slice to pull Mercury accounts and transactions into local SQLite, then show that data through `tally sync` and `tally status`.

### Decision

I am using sync `httpx` for the Mercury client because the CLI path is synchronous and this slice does not need async coordination yet. The live API matched the docs on base URL and endpoints, with Bearer auth working after using the full `secret-token:` token form and forcing IPv4 because the token is IP-whitelisted. I am using a 48-hour overlap window for incremental syncs so late-posting transactions are still picked up. I am adding a forward-only SQLite migration system in `tally/db.py` with a `schema_migrations` table and a first migration for `accounts.external_id`.

### Alternatives

I considered async `httpx`, but it would add ceremony without helping this CLI-only slice. I also considered storing Mercury balances directly, but the Phase 2 schema has no balance column and this slice only authorizes the `external_id` migration.

### Why

I want the ingest path to be small, idempotent, and easy to verify against the live account while preserving the schema boundary for later slices.
