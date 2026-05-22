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
    insert_position,
    run_migrations,
    update_account_synced_at,
    upsert_account,
    upsert_trade,
)
from tally.ingest.mercury import _last_synced_at, _parse_datetime
from tally.ingest.types import SyncResult

logger = structlog.get_logger()


DEFAULT_BASE_URL = "https://api.public.com"
USER_AGENT = f"tally-cfo/{__version__} (+https://github.com/wheelieinvestor/tally-cfo)"


class PublicAPIError(RuntimeError):
    pass


class PublicClient:
    def __init__(self, token: str, base_url: str | None = None) -> None:
        self.token = token
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._access_token: str | None = None
        self._client = httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            transport=httpx.HTTPTransport(local_address="0.0.0.0"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )

    def list_accounts(self) -> list[dict]:
        response = self._request("GET", "/userapigateway/trading/account")
        payload = response.json()
        if isinstance(payload, list):
            return payload
        return list(payload.get("accounts", []))

    def list_positions(self, account_id: str) -> list[dict]:
        portfolio = self.get_portfolio(account_id)
        return list(portfolio.get("positions") or [])

    def get_portfolio(self, account_id: str) -> dict:
        response = self._request(
            "GET",
            f"/userapigateway/trading/{account_id}/portfolio/v2",
            account_id=account_id,
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise PublicAPIError("Public portfolio response was not an object")
        return payload

    def list_trades(self, account_id: str, since: datetime | None = None) -> Iterator[dict]:
        params: dict[str, Any] = {"pageSize": 100}
        if since is not None:
            params["start"] = since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

        seen_tokens: set[str] = set()
        pages = 0
        while True:
            pages += 1
            if pages > 25:
                logger.warning(
                    "Stopped Public history pagination at page cap", account_id=account_id
                )
                break
            response = self._request(
                "GET",
                f"/userapigateway/trading/{account_id}/history",
                params=params,
                account_id=account_id,
            )
            payload = response.json()
            transactions = payload if isinstance(payload, list) else payload.get("transactions", [])
            if not transactions:
                break
            for transaction in transactions:
                try:
                    executed_at = _public_trade_time(transaction)
                except ValueError:
                    executed_at = None
                if since is None or executed_at is None or executed_at > since:
                    yield transaction

            next_token = None if isinstance(payload, list) else payload.get("nextToken")
            if not next_token:
                break
            if str(next_token) in seen_tokens:
                logger.warning(
                    "Stopped Public history pagination on repeated token", account_id=account_id
                )
                break
            seen_tokens.add(str(next_token))
            params["nextToken"] = next_token

    def sync(self, db_path: str | Path) -> SyncResult:
        started = time.monotonic()
        result = SyncResult()
        sync_finished_at = datetime.now(timezone.utc)

        try:
            accounts = self.list_accounts()
            with connect(db_path) as conn:
                run_migrations(conn)
                for account in accounts:
                    external_id = _require_text(account, "accountId")
                    portfolio = self.get_portfolio(external_id)
                    account_type = (
                        account.get("accountType") or portfolio.get("accountType") or "unknown"
                    )
                    account_name = _account_name(account, external_id)
                    account_id = upsert_account(
                        conn,
                        provider="public",
                        account_type=str(account_type),
                        account_name=account_name,
                        currency="USD",
                        external_id=external_id,
                        balance=_portfolio_balance(portfolio),
                    )
                    result.accounts_synced += 1

                    snapshot_at = sync_finished_at
                    for position in portfolio.get("positions") or []:
                        try:
                            insert_position(
                                conn,
                                account_id=account_id,
                                symbol=_position_symbol(position),
                                quantity=_decimal_field(position, "quantity"),
                                cost_basis=_position_cost_basis(position),
                                current_value=_optional_decimal(position.get("currentValue")),
                                snapshot_at=snapshot_at,
                            )
                        except (KeyError, ValueError, TypeError) as error:
                            logger.warning(
                                "Skipped Public position",
                                account_id=external_id,
                                error=str(error),
                            )
                            continue
                        result.positions_synced += 1

                    last_synced_at = _last_synced_at(conn, account_id)
                    since = None
                    if last_synced_at is not None:
                        since = last_synced_at - timedelta(hours=48)
                        logger.info(
                            "Using incremental Public window",
                            account_id=external_id,
                            since=since.isoformat(),
                        )

                    for trade in self.list_trades(external_id, since=since):
                        try:
                            parsed = _parse_trade(trade)
                            _, inserted = upsert_trade(
                                conn,
                                account_id=account_id,
                                external_id=parsed["external_id"],
                                symbol=parsed["symbol"],
                                side=parsed["side"],
                                quantity=parsed["quantity"],
                                price=parsed["price"],
                                executed_at=parsed["executed_at"],
                                raw_json=json.dumps(trade, sort_keys=True, default=str),
                            )
                        except (KeyError, ValueError, TypeError) as error:
                            result.trades_skipped += 1
                            logger.warning(
                                "Skipped Public trade",
                                account_id=external_id,
                                error=str(error),
                            )
                            continue
                        if inserted:
                            result.trades_inserted += 1
                        else:
                            result.trades_skipped += 1

                    update_account_synced_at(conn, account_id, sync_finished_at)
                    conn.commit()
                    logger.info(
                        "Synced Public account",
                        account_id=external_id,
                        positions_synced=result.positions_synced,
                        trades_inserted=result.trades_inserted,
                    )
        except PublicAPIError as error:
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
        self._ensure_access_token()
        endpoint = f"{self.base_url}{path}"
        attempts = 0
        while True:
            attempts += 1
            response = self._client.request(
                method,
                endpoint,
                params=params,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            if response.status_code < 400:
                return response
            if response.status_code == 401:
                self._access_token = None
                self._log_http_error(response, endpoint, account_id)
                raise PublicAPIError("Public rejected the token. Check PUBLIC_API_TOKEN.")
            if response.status_code == 429 and attempts <= 2:
                logger.warning(
                    "Public rate limit hit, retrying once",
                    account_id=account_id,
                    endpoint=endpoint,
                    status_code=response.status_code,
                )
                time.sleep(min(2**attempts, 30))
                continue
            if response.status_code >= 500 and attempts < 3:
                logger.warning(
                    "Public server error, retrying",
                    account_id=account_id,
                    endpoint=endpoint,
                    status_code=response.status_code,
                )
                time.sleep(min(2**attempts, 30))
                continue
            self._log_http_error(response, endpoint, account_id)
            raise PublicAPIError(
                f"Public request failed with HTTP {response.status_code}: {response.text[:200]}"
            )

    def _ensure_access_token(self) -> None:
        if self._access_token:
            return
        endpoint = f"{self.base_url}/userapiauthservice/personal/access-tokens"
        response = self._client.post(
            endpoint,
            json={"secret": self.token, "validityInMinutes": 15},
        )
        if response.status_code != 200:
            logger.error(
                "Public access token exchange failed",
                endpoint=endpoint,
                status_code=response.status_code,
                response_excerpt=response.text[:200],
            )
            raise PublicAPIError(
                f"Public access token exchange failed with HTTP {response.status_code}"
            )
        token = response.json().get("accessToken")
        if not token:
            raise PublicAPIError("Public access token exchange did not return accessToken")
        self._access_token = str(token)

    def _log_http_error(
        self, response: httpx.Response, endpoint: str, account_id: str | None
    ) -> None:
        logger.error(
            "Public request failed",
            account_id=account_id,
            endpoint=endpoint,
            status_code=response.status_code,
            response_excerpt=response.text[:200],
        )


def _require_text(data: dict, key: str) -> str:
    value = data.get(key)
    if value is None or value == "":
        raise KeyError(f"missing {key}")
    return str(value)


def _account_name(account: dict, account_id: str) -> str:
    account_type = str(account.get("accountType") or "Account").replace("_", " ")
    brokerage_type = account.get("brokerageAccountType")
    if brokerage_type:
        return f"Public {account_type.title()} {str(brokerage_type).replace('_', ' ').title()}"
    return f"Public {account_type.title()} {account_id[-4:]}"


def _portfolio_balance(portfolio: dict) -> Decimal | None:
    equity = portfolio.get("equity") or []
    if equity:
        total = Decimal("0")
        for item in equity:
            value = _optional_decimal(item.get("value"))
            if value is not None:
                total += value
        return total
    buying_power = portfolio.get("buyingPower") or {}
    return _optional_decimal(
        buying_power.get("cashOnlyBuyingPower") or buying_power.get("buyingPower")
    )


def _position_symbol(position: dict) -> str:
    instrument = position.get("instrument") or {}
    symbol = instrument.get("symbol") or position.get("symbol") or position.get("ticker")
    if not symbol:
        raise KeyError("missing symbol")
    return str(symbol)


def _position_cost_basis(position: dict) -> Decimal | None:
    cost_basis = position.get("costBasis") or {}
    return _optional_decimal(
        cost_basis.get("totalCost")
        or position.get("costBasis")
        or position.get("totalCost")
        or position.get("totalCostBasis")
    )


def _decimal_field(data: dict, key: str) -> Decimal:
    value = data.get(key)
    if value is None:
        raise KeyError(f"missing {key}")
    return Decimal(str(value))


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _parse_trade(trade: dict) -> dict:
    transaction_type = str(trade.get("type") or trade.get("transactionType") or "").upper()
    if transaction_type and transaction_type != "TRADE":
        raise ValueError("not a trade")

    side = str(trade.get("side") or trade.get("orderSide") or "").lower()
    if side not in {"buy", "sell"}:
        raise ValueError("not a buy/sell trade")

    instrument = trade.get("instrument") or {}
    symbol = instrument.get("symbol") or trade.get("symbol")
    if not symbol:
        raise KeyError("missing symbol")

    external_id = (
        trade.get("transactionId")
        or trade.get("orderId")
        or trade.get("id")
        or trade.get("historyId")
    )
    if not external_id:
        raise KeyError("missing external id")

    quantity = _optional_decimal(
        trade.get("filledQuantity") or trade.get("quantity") or trade.get("executedQuantity")
    )
    price = _optional_decimal(
        trade.get("averagePrice") or trade.get("price") or trade.get("executedPrice")
    )
    principal = _optional_decimal(trade.get("principalAmount") or trade.get("netAmount"))
    if price is None and principal is not None and quantity not in (None, Decimal("0")):
        price = abs(principal / quantity)
    if quantity is None or price is None:
        raise KeyError("missing quantity or price")

    return {
        "external_id": str(external_id),
        "symbol": str(symbol),
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": _public_trade_time(trade),
    }


def _public_trade_time(trade: dict) -> datetime:
    for key in ("executedAt", "filledAt", "closedAt", "createdAt", "timestamp"):
        value = trade.get(key)
        if value:
            return _parse_datetime(value)
    raise ValueError("missing trade timestamp")
