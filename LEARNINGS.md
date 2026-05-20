# Learnings

## 2026-05-20: Mercury ingest

Mercury account and transaction endpoints worked as documented, but this token required the full `secret-token:` prefix and IPv4 because the token whitelist rejected rotating IPv6 privacy addresses.
