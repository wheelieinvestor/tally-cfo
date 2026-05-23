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

## 2026-05-20: Slice 2: Public ingest, balance fix, and status formatting

### Context

I need `tally sync` to pull Mercury plus Public into SQLite, store real account balances, and make `tally status` display accounts, recent transactions, and Public positions with stable formatting.

### Decision

Public uses `https://api.public.com` with a long-lived personal secret exchanged at `POST /userapiauthservice/personal/access-tokens`, then `Authorization: Bearer <accessToken>` for API calls. The live docs matched the API once the correct secret was saved. Public account listing returns account metadata only, while portfolio v2 returns `positions`, `equity`, `buyingPower`, and account value data. I am treating Public positions as snapshot-only rows and querying current positions with `get_latest_positions`.

Mercury balance uses `currentBalance`, with `availableBalance` only as a fallback because `currentBalance` is the settled account balance that matches the account UI. Public balance uses the sum of portfolio v2 `equity[].value`, falling back to buying power only when equity is absent. Status now reads `accounts.balance` directly instead of summing transactions. Money formatting now puts the sign outside the dollar symbol, transaction lines are forced to one physical line with fixed columns, and NULL categories render as `--`.

### Alternatives

I considered deriving Public value from `buyingPower`, but that would ignore invested equity. I considered upserting positions by account and symbol, but keeping every snapshot preserves later trend analysis. I considered preserving the transaction-derived balance as a fallback, but that would keep the original correctness bug alive.

### Why

The slice needs the local database to reflect provider-reported balances and live brokerage snapshots exactly, while keeping sync idempotent for trades and preserving historical position snapshots for future slices.

## 2026-05-22: Slice 3: Agent core, tally ask, and the voice decision

### Context

I need the first real agent path to answer one user question from real local Mercury and Public data, store the exchange, and optionally push the answer to Telegram.

### Decision

I am shipping Level 1 voice for this slice: dry and observational, not Level 3 full-spice. Starting dry beats starting performatively spicy; the voice can sharpen later after we see how it lands against real data.

The agent uses `claude-sonnet-4-5` with non-streaming sync calls and a 1024 token cap because this path is one question, one grounded answer, then exit. The context builder is rule-based for slice 3: accounts are always included, transactions and brokerage data are included when keywords imply they are relevant, and the last 6 conversation turns are read from SQLite every time. Later slices can evolve this into a tool-call pattern if the rules get too wide.

Conversation storage stays in the existing `conversations` table. Each `tally ask` call writes one user row and one agent row with `surface='cli'`; both rows share a short random `thread_id` so a single exchange can be inspected while still letting future context read the latest turns across threads.

### Alternatives

I considered pushing toward the sharper Phase 0 voice now, but that risks making early factual answers feel forced. I also considered dumping the whole database into the prompt, but that would hide context bugs and waste tokens.

### Why

The product needs answers that are useful before they are theatrical. A narrow agent path with explicit context and stored turns gives later slices a stable base.
