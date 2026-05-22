# Learnings

## 2026-05-20: Mercury ingest

Mercury account and transaction endpoints worked as documented, but this token required the full `secret-token:` prefix and IPv4 because the token whitelist rejected rotating IPv6 privacy addresses.

## 2026-05-20: Public ingest

Public auth is a two-step flow: exchange the personal secret for a short-lived access token, then use Bearer auth. The account endpoint has no balances, so account value comes from portfolio v2. Live portfolio responses can have zero positions and empty equity for one account, so the ingest path needs to tolerate empty snapshots. History pagination uses `nextToken`, and live history returns a top-level `transactions` array rather than a `trades` key.

The balance bug came from the local status query deriving account balance from transaction sums. Provider-reported balances need their own `accounts.balance` column and status should show `--` until a provider has synced a real balance.
