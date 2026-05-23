import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from tally.db import get_all_accounts, get_latest_positions, get_recent_conversations

MAX_CONTEXT_CHARS = 8000 * 4
TRANSACTION_LIMIT = 100
TRADE_LIMIT = 20

TRANSACTION_RE = re.compile(
    r"\b(transaction|transactions|spent|spending|spend|vendor|date|recent|money|charge|charges|expense|expenses|burn|cash|this month|last month|this week|last week|today|yesterday)\b",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
SUBSCRIPTION_RE = re.compile(r"\b(subscription|subscriptions|recurring)\b", re.IGNORECASE)
PORTFOLIO_RE = re.compile(
    r"\b(position|positions|portfolio|stock|stocks|shares|invest|invested|investment|brokerage|ticker|trade|trades)\b",
    re.IGNORECASE,
)
TICKER_RE = re.compile(r"\b[A-Z]{4}\b")


def build_context_for_query(db_conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    context: dict[str, Any] = {
        "accounts": get_all_accounts(db_conn),
        "transactions": [],
        "positions": [],
        "trades": [],
        "recent_conversations": get_recent_conversations(db_conn, 6),
        "context_notes": [],
    }

    if _wants_transactions(query):
        context["transactions"] = _recent_transactions(db_conn)

    if _wants_subscriptions(query):
        context["subscriptions_note"] = "subscription detection not yet implemented"

    if _wants_portfolio(query):
        context["positions"] = get_latest_positions(db_conn)
        context["trades"] = _recent_trades(db_conn)

    _cap_context(context)
    return context


def _wants_transactions(query: str) -> bool:
    return bool(TRANSACTION_RE.search(query) or DATE_RE.search(query))


def _wants_subscriptions(query: str) -> bool:
    return bool(SUBSCRIPTION_RE.search(query))


def _wants_portfolio(query: str) -> bool:
    return bool(PORTFOLIO_RE.search(query) or TICKER_RE.search(query))


def _recent_transactions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    rows = conn.execute(
        """
        SELECT
          transactions.posted_at,
          transactions.amount,
          transactions.description,
          transactions.counterparty,
          transactions.category,
          accounts.account_name,
          accounts.provider
        FROM transactions
        JOIN accounts ON accounts.id = transactions.account_id
        WHERE transactions.posted_at >= ?
        ORDER BY transactions.posted_at DESC, transactions.id DESC
        LIMIT ?
        """,
        (cutoff, TRANSACTION_LIMIT),
    ).fetchall()
    return [dict(row) for row in rows]


def _recent_trades(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          trades.executed_at,
          trades.symbol,
          trades.side,
          trades.quantity,
          trades.price,
          accounts.account_name,
          accounts.provider
        FROM trades
        JOIN accounts ON accounts.id = trades.account_id
        ORDER BY trades.executed_at DESC, trades.id DESC
        LIMIT ?
        """,
        (TRADE_LIMIT,),
    ).fetchall()
    return [dict(row) for row in rows]


def _cap_context(context: dict[str, Any]) -> None:
    while _estimated_chars(context) > MAX_CONTEXT_CHARS and context.get("transactions"):
        context["transactions"].pop()
        context["context_notes"].append("transactions truncated to fit context budget")
    while _estimated_chars(context) > MAX_CONTEXT_CHARS and context.get("trades"):
        context["trades"].pop()
        context["context_notes"].append("trades truncated to fit context budget")
    while _estimated_chars(context) > MAX_CONTEXT_CHARS and context.get("recent_conversations"):
        context["recent_conversations"].pop(0)
        context["context_notes"].append("conversation history truncated to fit context budget")


def _estimated_chars(context: dict[str, Any]) -> int:
    return len(str(context))
