import sqlite3
from pathlib import Path

from tally.config import home_dir


def default_db_path() -> Path:
    return home_dir() / "tally.db"


def schema() -> str:
    return """
CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL CHECK(provider IN ('mercury','public')),
  account_type TEXT NOT NULL,
  account_name TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  last_synced_at TIMESTAMP
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
    return sqlite3.connect(db_path)


def run_migrations(connection: sqlite3.Connection) -> None:
    connection.executescript(schema())
    connection.commit()


def init_db(path: Path | str | None = None) -> Path:
    db_path = Path(path) if path else default_db_path()
    with connect(db_path) as connection:
        run_migrations(connection)
    return db_path
