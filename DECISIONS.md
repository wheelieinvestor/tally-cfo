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
