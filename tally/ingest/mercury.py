import json
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import structlog

from tally import __version__
from tally.db import (
    connect,
    run_migrations,
    update_account_synced_at,
    upsert_account,
    upsert_transaction,
)
from tally.ingest.types import SyncResult

logger = structlog.get_logger()


DEFAULT_BASE_URL = "https://api.mercury.com/api/v1"
USER_AGENT = f"tally-cfo/{__version__} (+https://github.com/wheelieinvestor/tally-cfo)"


class MercuryAPIError(RuntimeError):
    pass


class MercuryClient:
    def __init__(self, token: str, base_url: str | None = None) -> None:
        self.token = token if token.startswith("secret-token:") else f"secret-token:{token}"
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._client = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            transport=httpx.HTTPTransport(local_address="0.0.0.0"),
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )

    def list_accounts(self) -> list[dict]:
        response = self._request("GET", "/accounts", params={"limit": 1000})
        payload = response.json()
        if isinstance(payload, list):
            return payload
        return list(payload.get("accounts", []))

    def list_transactions(self, account_id: str, since: datetime | None = None) -> Iterator[dict]:
        limit = 1000
        offset = 0
        params: dict[str, Any] = {"limit": limit, "offset": offset, "order": "desc"}
        if since is not None:
            params["start"] = since.astimezone(timezone.utc).date().isoformat()

        while True:
            params["offset"] = offset
            response = self._request(
                "GET",
                f"/account/{account_id}/transactions",
                params=params,
                account_id=account_id,
            )
            payload = response.json()
            transactions = payload if isinstance(payload, list) else payload.get("transactions", [])
            if not transactions:
                break

            for transaction in transactions:
                posted_at = _parse_datetime(
                    transaction.get("postedAt") or transaction.get("createdAt")
                )
                if since is None or posted_at > since:
                    yield transaction

            if len(transactions) < limit:
                break
            offset += limit

    def sync(self, db_path: str | Path) -> SyncResult:
        started = time.monotonic()
        result = SyncResult()
        sync_finished_at = datetime.now(timezone.utc)

        try:
            accounts = self.list_accounts()
            with connect(db_path) as conn:
                run_migrations(conn)
                for account in accounts:
                    external_id = _require_text(account, "id")
                    account_name = (
                        account.get("name") or account.get("nickname") or f"Mercury {external_id}"
                    )
                    account_type = account.get("kind") or account.get("type") or "unknown"
                    currency = account.get("currency") or "USD"
                    balance = _account_balance(account)
                    account_id = upsert_account(
                        conn,
                        provider="mercury",
                        account_type=str(account_type),
                        account_name=str(account_name),
                        currency=str(currency),
                        external_id=external_id,
                        balance=balance,
                    )
                    result.accounts_synced += 1

                    last_synced_at = _last_synced_at(conn, account_id)
                    since = None
                    if last_synced_at is not None:
                        since = last_synced_at - timedelta(hours=48)
                        logger.info(
                            "Using incremental Mercury window",
                            account_id=external_id,
                            since=since.isoformat(),
                        )

                    for transaction in self.list_transactions(external_id, since=since):
                        try:
                            _, inserted = upsert_transaction(
                                conn,
                                account_id=account_id,
                                external_id=_require_text(transaction, "id"),
                                posted_at=_parse_datetime(
                                    transaction.get("postedAt") or transaction.get("createdAt")
                                ),
                                amount=Decimal(str(transaction.get("amount"))),
                                description=_description(transaction),
                                counterparty=_counterparty(transaction),
                                category=_category(transaction),
                                raw_json=json.dumps(transaction, sort_keys=True, default=str),
                            )
                        except (KeyError, ValueError, TypeError) as error:
                            result.transactions_skipped += 1
                            logger.warning(
                                "Skipped Mercury transaction",
                                account_id=external_id,
                                error=str(error),
                            )
                            continue
                        if inserted:
                            result.transactions_inserted += 1
                        else:
                            result.transactions_skipped += 1

                    update_account_synced_at(conn, account_id, sync_finished_at)
                    conn.commit()
                    logger.info(
                        "Synced Mercury account",
                        account_id=external_id,
                        transactions_inserted=result.transactions_inserted,
                    )
        except MercuryAPIError as error:
            result.errors.append(str(error))
        finally:
            self._client.close()
            result.duration_seconds = time.monotonic() - started

        return result

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        account_id: str | None = None,
    ) -> httpx.Response:
        endpoint = f"{self.base_url}{path}"
        attempts = 0
        while True:
            attempts += 1
            response = self._client.request(method, endpoint, params=params)
            if response.status_code < 400:
                return response
            if response.status_code == 401:
                self._log_http_error(response, endpoint, account_id)
                raise MercuryAPIError(
                    "Mercury rejected the token. Check MERCURY_API_TOKEN, include secret-token:, "
                    "and confirm the current IP is whitelisted."
                )
            if response.status_code == 429 and attempts <= 2:
                logger.warning(
                    "Mercury rate limit hit, retrying once",
                    account_id=account_id,
                    endpoint=endpoint,
                    status_code=response.status_code,
                )
                time.sleep(min(2**attempts, 30))
                continue
            if response.status_code >= 500 and attempts < 3:
                logger.warning(
                    "Mercury server error, retrying",
                    account_id=account_id,
                    endpoint=endpoint,
                    status_code=response.status_code,
                )
                time.sleep(min(2**attempts, 30))
                continue
            self._log_http_error(response, endpoint, account_id)
            raise MercuryAPIError(
                f"Mercury request failed with HTTP {response.status_code}: {response.text[:200]}"
            )

    def _log_http_error(
        self, response: httpx.Response, endpoint: str, account_id: str | None
    ) -> None:
        logger.error(
            "Mercury request failed",
            account_id=account_id,
            endpoint=endpoint,
            status_code=response.status_code,
            response_excerpt=response.text[:200],
        )


def _last_synced_at(conn: Any, account_id: int) -> datetime | None:
    row = conn.execute("SELECT last_synced_at FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None or not row["last_synced_at"]:
        return None
    return _parse_datetime(row["last_synced_at"])


def _parse_datetime(value: Any) -> datetime:
    if not value:
        raise ValueError("missing timestamp")
    text = str(value)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _require_text(data: dict, key: str) -> str:
    value = data.get(key)
    if value is None or value == "":
        raise KeyError(f"missing {key}")
    return str(value)


def _description(transaction: dict) -> str | None:
    for key in ("note", "externalMemo", "bankDescription", "kind"):
        value = transaction.get(key)
        if value:
            return str(value)
    return None


def _counterparty(transaction: dict) -> str | None:
    for key in ("counterpartyName", "counterpartyNickname", "merchant"):
        value = transaction.get(key)
        if value:
            return str(value)
    return None


def _category(transaction: dict) -> str | None:
    category = transaction.get("mercuryCategory")
    if category:
        return str(category)
    category_data = transaction.get("categoryData")
    if isinstance(category_data, dict):
        for key in ("name", "category", "label"):
            value = category_data.get(key)
            if value:
                return str(value)
    return None


def _account_balance(account: dict) -> Decimal | None:
    current = account.get("currentBalance")
    available = account.get("availableBalance")
    if current is not None and available is not None and str(current) != str(available):
        logger.info(
            "Mercury current and available balances differ",
            account_id=account.get("id"),
        )
    if current is None:
        current = available
    if current is None:
        return None
    return Decimal(str(current))
