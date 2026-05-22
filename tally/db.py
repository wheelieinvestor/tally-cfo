import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from tally.config import home_dir


def default_db_path() -> Path:
    return home_dir() / "tally.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def schema() -> str:
    return """
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL CHECK(provider IN ('mercury','public')),
  external_id TEXT,
  account_type TEXT NOT NULL,
  account_name TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  last_synced_at TIMESTAMP,
  UNIQUE(provider, external_id)
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  external_id TEXT NOT NULL,
  posted_at TIMESTAMP NOT NULL,
  amount NUMERIC NOT NULL,
  description TEXT,
  counterparty TEXT,
  category TEXT,
  is_recurring INTEGER NOT NULL DEFAULT 0,
  raw_json TEXT,
  UNIQUE(account_id, external_id)
);

CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  symbol TEXT NOT NULL,
  quantity NUMERIC NOT NULL,
  cost_basis NUMERIC,
  current_value NUMERIC,
  snapshot_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES accounts(id),
  external_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK(side IN ('buy','sell')),
  quantity NUMERIC NOT NULL,
  price NUMERIC NOT NULL,
  executed_at TIMESTAMP NOT NULL,
  raw_json TEXT,
  UNIQUE(account_id, external_id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  vendor_pattern TEXT NOT NULL,
  monthly_amount NUMERIC,
  last_charge_at TIMESTAMP,
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','cancelled','flagged')),
  first_seen_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS derived_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL UNIQUE,
  value TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0.5,
  updated_at TIMESTAMP NOT NULL,
  source TEXT
);

CREATE TABLE IF NOT EXISTS briefs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  generated_at TIMESTAMP NOT NULL,
  period_start TIMESTAMP NOT NULL,
  period_end TIMESTAMP NOT NULL,
  markdown_body TEXT NOT NULL,
  key_facts_json TEXT
);

CREATE TABLE IF NOT EXISTS receipts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  generated_at TIMESTAMP NOT NULL,
  month TEXT NOT NULL UNIQUE,
  markdown_body TEXT NOT NULL,
  image_path TEXT,
  key_facts_json TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  surface TEXT NOT NULL CHECK(surface IN ('telegram','cli')),
  role TEXT NOT NULL CHECK(role IN ('user','agent')),
  content TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL,
  thread_id TEXT
);

CREATE TABLE IF NOT EXISTS notifications_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sent_at TIMESTAMP NOT NULL,
  surface TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('brief','receipt','ambient')),
  content_summary TEXT,
  triggered_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_transactions_account_posted ON transactions(account_id, posted_at);
CREATE INDEX IF NOT EXISTS idx_positions_account_snapshot ON positions(account_id, snapshot_at);
CREATE INDEX IF NOT EXISTS idx_trades_account_executed ON trades(account_id, executed_at);
CREATE INDEX IF NOT EXISTS idx_conversations_thread ON conversations(thread_id, created_at);
""".strip()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path else default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    connection.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
          name TEXT PRIMARY KEY,
          applied_at TIMESTAMP NOT NULL
        )
        """)


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _migration_001_accounts_external_id(connection: sqlite3.Connection) -> None:
    if not _column_exists(connection, "accounts", "external_id"):
        connection.execute("ALTER TABLE accounts ADD COLUMN external_id TEXT")
    connection.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_provider_external_id
        ON accounts(provider, external_id)
        """)


def _migration_002_accounts_balance(connection: sqlite3.Connection) -> None:
    if not _column_exists(connection, "accounts", "balance"):
        connection.execute("ALTER TABLE accounts ADD COLUMN balance NUMERIC")


Migration = tuple[str, Callable[[sqlite3.Connection], None]]


def migrations() -> list[Migration]:
    return [
        ("001_accounts_external_id", _migration_001_accounts_external_id),
        ("002_accounts_balance", _migration_002_accounts_balance),
    ]


def run_migrations(connection: sqlite3.Connection) -> None:
    connection.executescript(schema())
    _ensure_migration_table(connection)
    applied = {
        row["name"] for row in connection.execute("SELECT name FROM schema_migrations").fetchall()
    }
    for name, migration in migrations():
        if name in applied:
            continue
        migration(connection)
        connection.execute(
            "INSERT INTO schema_migrations(name, applied_at) VALUES (?, ?)",
            (name, utc_now()),
        )
    connection.commit()


def init_db(path: Path | str | None = None) -> Path:
    db_path = Path(path) if path else default_db_path()
    with connect(db_path) as connection:
        run_migrations(connection)
    return db_path


def upsert_account(
    conn: sqlite3.Connection,
    provider: str,
    account_type: str,
    account_name: str,
    currency: str,
    external_id: str,
    balance: Decimal | None,
) -> int:
    conn.execute(
        """
        INSERT INTO accounts(provider, external_id, account_type, account_name, currency, balance)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider, external_id) DO UPDATE SET
          account_type = excluded.account_type,
          account_name = excluded.account_name,
          currency = excluded.currency,
          balance = excluded.balance
        """,
        (
            provider,
            external_id,
            account_type,
            account_name,
            currency,
            str(balance) if balance is not None else None,
        ),
    )
    row = conn.execute(
        "SELECT id FROM accounts WHERE provider = ? AND external_id = ?",
        (provider, external_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("Account upsert failed")
    return int(row["id"])


def upsert_transaction(
    conn: sqlite3.Connection,
    account_id: int,
    external_id: str,
    posted_at: datetime,
    amount: Decimal,
    description: str | None,
    counterparty: str | None,
    category: str | None,
    raw_json: str,
) -> tuple[int, bool]:
    posted = posted_at.astimezone(timezone.utc).isoformat()
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO transactions(
          account_id, external_id, posted_at, amount, description, counterparty, category, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            external_id,
            posted,
            str(amount),
            description,
            counterparty,
            category,
            raw_json,
        ),
    )
    was_inserted = cursor.rowcount == 1
    row = conn.execute(
        "SELECT id FROM transactions WHERE account_id = ? AND external_id = ?",
        (account_id, external_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("Transaction upsert failed")
    return int(row["id"]), was_inserted


def update_account_synced_at(conn: sqlite3.Connection, account_id: int, when: datetime) -> None:
    conn.execute(
        "UPDATE accounts SET last_synced_at = ? WHERE id = ?",
        (when.astimezone(timezone.utc).isoformat(), account_id),
    )


def insert_position(
    conn: sqlite3.Connection,
    account_id: int,
    symbol: str,
    quantity: Decimal,
    cost_basis: Decimal | None,
    current_value: Decimal | None,
    snapshot_at: datetime,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO positions(account_id, symbol, quantity, cost_basis, current_value, snapshot_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            symbol,
            str(quantity),
            str(cost_basis) if cost_basis is not None else None,
            str(current_value) if current_value is not None else None,
            snapshot_at.astimezone(timezone.utc).isoformat(),
        ),
    )
    return int(cursor.lastrowid)


def upsert_trade(
    conn: sqlite3.Connection,
    account_id: int,
    external_id: str,
    symbol: str,
    side: str,
    quantity: Decimal,
    price: Decimal,
    executed_at: datetime,
    raw_json: str,
) -> tuple[int, bool]:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO trades(
          account_id, external_id, symbol, side, quantity, price, executed_at, raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            external_id,
            symbol,
            side,
            str(quantity),
            str(price),
            executed_at.astimezone(timezone.utc).isoformat(),
            raw_json,
        ),
    )
    was_inserted = cursor.rowcount == 1
    row = conn.execute(
        "SELECT id FROM trades WHERE account_id = ? AND external_id = ?",
        (account_id, external_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("Trade upsert failed")
    return int(row["id"]), was_inserted


def get_latest_positions(conn: sqlite3.Connection, account_id: int | None = None) -> list[dict]:
    params: tuple[int, ...] = () if account_id is None else (account_id,)
    account_filter = "" if account_id is None else "AND positions.account_id = ?"
    rows = conn.execute(
        f"""
        SELECT *
        FROM (
          SELECT
            positions.*,
            accounts.account_name,
            accounts.provider,
            ROW_NUMBER() OVER (
              PARTITION BY positions.account_id, positions.symbol
              ORDER BY positions.snapshot_at DESC, positions.id DESC
            ) AS row_number
          FROM positions
          JOIN accounts ON accounts.id = positions.account_id
          WHERE accounts.provider = 'public'
          {account_filter}
        )
        WHERE row_number = 1
        ORDER BY CAST(current_value AS NUMERIC) DESC, symbol
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def get_all_accounts(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT *
        FROM accounts
        ORDER BY provider, account_name
        """).fetchall()
    return [dict(row) for row in rows]


def get_accounts_by_provider(conn: sqlite3.Connection, provider: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT accounts.*
        FROM accounts
        WHERE accounts.provider = ?
        ORDER BY accounts.account_name
        """,
        (provider,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_recent_transactions(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
          transactions.*,
          accounts.account_name,
          accounts.provider
        FROM transactions
        JOIN accounts ON accounts.id = transactions.account_id
        ORDER BY transactions.posted_at DESC, transactions.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
