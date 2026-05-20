from datetime import datetime, timezone
from decimal import Decimal
from shutil import copyfile

import click

from tally.config import home_dir, repo_root
from tally.db import (
    connect,
    get_accounts_by_provider,
    get_recent_transactions,
    init_db,
    run_migrations,
)
from tally.ingest.orchestrator import sync_all
from tally.logging_setup import setup_logging


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
    setup_logging()
    init_db()
    results = sync_all(["mercury"])
    has_errors = False
    for provider, result in results.items():
        click.echo(
            f"{provider}: {result.accounts_synced} accounts synced, "
            f"{result.transactions_inserted} new transactions, "
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
        accounts = get_accounts_by_provider(conn, "mercury")
        if not accounts:
            click.echo("No data yet. Run `tally sync`.")
            return
        transactions = get_recent_transactions(conn, 10)

    click.echo(f"Accounts ({len(accounts)})")
    for account in accounts:
        name = str(account["account_name"])
        # Mercury transaction responses do not include running balance, so this slice displays
        # the transaction-derived account total from the local ledger.
        balance = _money(Decimal(str(account.get("derived_balance") or "0")))
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
        category = transaction.get("category") or ""
        styled_amount = click.style(amount_text, fg="green" if amount >= 0 else "red")
        click.echo(f"  {posted_at}  {str(name)[:18]:<18} {styled_amount:>12}   {category}")


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
@click.argument("question")
def ask(question: str) -> None:
    _not_implemented("ask")


@click.command()
def facts() -> None:
    _not_implemented("facts")


@click.command()
@click.argument("thing")
def why(thing: str) -> None:
    _not_implemented("why")


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


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
