from datetime import datetime, timezone
from decimal import Decimal
from shutil import copyfile
from uuid import uuid4

import click
import structlog

from tally.agent.context import build_context_for_query
from tally.agent.core import AgentContext, UserQueryTrigger, run_agent
from tally.config import home_dir, repo_root
from tally.db import (
    connect,
    get_all_accounts,
    get_latest_positions,
    get_recent_transactions,
    get_recent_conversations,
    init_db,
    insert_conversation_turn,
    run_migrations,
    utc_now,
)
from tally.logging_setup import setup_logging

LOGGER = structlog.get_logger(__name__)


def _not_implemented(command_name: str) -> None:
    click.echo(f"{command_name}: not implemented yet")


@click.command()
def setup() -> None:
    setup_logging()
    tally_dir = home_dir()
    logs_dir = tally_dir / "logs"
    env_file = tally_dir / ".env"
    example_env = repo_root() / ".env.example"

    tally_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    click.echo(f"Using {tally_dir}")
    click.echo(f"Using {logs_dir}")

    if env_file.exists():
        click.echo(f"Env file already exists: {env_file}")
    else:
        copyfile(example_env, env_file)
        click.echo(f"Created env file: {env_file}")

    db_path = init_db()
    click.echo(f"Database ready: {db_path}")

    click.echo("")
    click.echo("Next steps:")
    click.echo(f"1. Fill in API keys in {env_file}")
    click.echo("2. Register a Telegram bot with BotFather")
    click.echo("3. Add your Telegram user ID")
    click.echo("4. Run tally status")


@click.command()
def sync() -> None:
    from tally.ingest.orchestrator import sync_all

    setup_logging()
    init_db()
    results = sync_all()
    has_errors = False
    for provider, result in results.items():
        if provider == "public":
            click.echo(
                f"{provider}: {result.accounts_synced} {_plural('account', result.accounts_synced)} "
                f"synced, {result.positions_synced} positions, "
                f"{result.trades_inserted} new {_plural('trade', result.trades_inserted)}, "
                f"{result.duration_seconds:.1f}s"
            )
        else:
            click.echo(
                f"{provider}: {result.accounts_synced} {_plural('account', result.accounts_synced)} "
                f"synced, {result.transactions_inserted} new transactions, "
                f"{result.duration_seconds:.1f}s"
            )
        for error in result.errors:
            has_errors = True
            click.echo(f"{provider} error: {error}")
    raise click.exceptions.Exit(1 if has_errors else 0)


@click.command()
def status() -> None:
    setup_logging()
    db_path = init_db()
    with connect(db_path) as conn:
        run_migrations(conn)
        accounts = get_all_accounts(conn)
        if not accounts:
            click.echo("No data yet. Run `tally sync`.")
            return
        transactions = get_recent_transactions(conn, 10)
        positions = get_latest_positions(conn)

    click.echo(f"Accounts ({len(accounts)})")
    for account in accounts:
        name = str(account["account_name"])
        balance = _money_or_dash(account.get("balance"))
        synced = _relative_time(str(account.get("last_synced_at") or ""))
        dots = "." * max(2, 32 - len(name))
        click.echo(f"  {name} {dots} {balance:<12} (synced {synced})")

    click.echo("")
    click.echo("Recent transactions")
    for transaction in transactions:
        posted_at = _display_date(str(transaction["posted_at"]))
        name = transaction.get("counterparty") or transaction.get("description") or "Unknown"
        amount = Decimal(str(transaction["amount"]))
        amount_text = _signed_money(amount)
        category = _single_line(transaction.get("category") or "--")[:16]
        amount_cell = f"{amount_text:>10}"
        styled_amount = click.style(amount_cell, fg="green" if amount >= 0 else "red")
        click.echo(f"{posted_at}  {_fixed_text(str(name), 34)}  " f"{styled_amount}     {category}")

    if positions:
        visible = positions[:20]
        click.echo("")
        click.echo(f"Positions ({len(positions)})")
        for position in visible:
            click.echo(f"  {_position_line(position)}")
        remaining = len(positions) - len(visible)
        if remaining > 0:
            click.echo(f"  + {remaining} more")


@click.command()
@click.option("--push", is_flag=True)
def brief(push: bool) -> None:
    _not_implemented("brief")


@click.command()
@click.option("--month")
@click.option("--push", is_flag=True)
def receipt(month: str | None, push: bool) -> None:
    _not_implemented("receipt")


@click.command()
@click.option("--push", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.argument("question")
def ask(question: str, push: bool, dry_run: bool) -> None:
    setup_logging()
    db_path = init_db()
    thread_id = uuid4().hex[:10]
    with connect(db_path) as conn:
        run_migrations(conn)
        context_data = build_context_for_query(conn, question)
        context = AgentContext(
            data=context_data,
            user_question=question,
            recent_conversations=get_recent_conversations(conn, 6),
        )
        trigger = UserQueryTrigger(query=question)
        try:
            output = run_agent(trigger, context)
        except Exception as error:
            LOGGER.warning("ask_failed", error=str(error))
            click.echo(f"claude api error: {_short_error(error)}", err=True)
            raise click.exceptions.Exit(1) from error

        now = datetime.fromisoformat(utc_now())
        insert_conversation_turn(conn, "cli", "user", question, thread_id, now)
        insert_conversation_turn(conn, "cli", "agent", output.text, thread_id, now)
        conn.commit()

    click.echo(output.text)
    if push and dry_run:
        click.echo("[dry-run] would push to telegram")
        return
    if push:
        from tally.surfaces.telegram_bot import send_to_user

        try:
            send_to_user(output.text)
        except Exception as error:
            LOGGER.warning("telegram_push_from_ask_failed", error=str(error))
            click.echo(f"telegram push error: {_short_error(error)}", err=True)
            raise click.exceptions.Exit(1) from error


@click.command()
def facts() -> None:
    _not_implemented("facts")


@click.command()
@click.argument("thing")
def why(thing: str) -> None:
    _not_implemented("why")


def _money(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _money_or_dash(value: object) -> str:
    if value is None or value == "":
        return "--"
    return _money(Decimal(str(value)))


def _signed_money(value: Decimal) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.2f}"


def _display_date(value: str) -> str:
    return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d")


def _relative_time(value: str) -> str:
    if not value:
        return "never"
    try:
        then = datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return "unknown"
    delta = datetime.now(timezone.utc) - then
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _plural(word: str, count: int) -> str:
    return word if count == 1 else f"{word}s"


def _single_line(value: str) -> str:
    return " ".join(str(value).split())


def _fixed_text(value: str, width: int) -> str:
    text = _single_line(value)
    if len(text) > width:
        text = f"{text[: width - 1]}…"
    return f"{text:<{width}}"


def _quantity_text(value: Decimal) -> str:
    if value == value.to_integral_value():
        text = f"{value:.0f}"
    else:
        text = f"{value.normalize():f}".rstrip("0").rstrip(".")
    noun = "share" if value == Decimal("1") else "shares"
    return f"{text} {noun}"


def _position_line(position: dict) -> str:
    symbol = str(position["symbol"])
    quantity = Decimal(str(position["quantity"]))
    current_value = Decimal(str(position["current_value"] or "0"))
    cost_basis_raw = position.get("cost_basis")
    avg_text = "--"
    change_text = ""
    if cost_basis_raw not in (None, "") and quantity != 0:
        cost_basis = Decimal(str(cost_basis_raw))
        avg_text = _money(cost_basis / quantity)
        change = current_value - cost_basis
        percent = Decimal("0") if cost_basis == 0 else (change / cost_basis) * Decimal("100")
        sign = "+" if change >= 0 else ""
        percent_text = f"{sign}{percent:.1f}%"
        money_text = f"{sign}{_money(change)}" if change >= 0 else _money(change)
        color = "green" if change > 0 else "red" if change < 0 else None
        change_text = "   " + click.style(f"({percent_text} / {money_text})", fg=color)
    left = f"{symbol} {_dots(symbol)} {_quantity_text(quantity)} @ avg {avg_text}"
    return f"{left} = {_money(current_value):<12}{change_text}"


def _dots(symbol: str) -> str:
    return "." * max(2, 18 - len(symbol))


def _short_error(error: Exception) -> str:
    text = " ".join(str(error).split())
    if not text:
        return error.__class__.__name__
    return text[:180]
