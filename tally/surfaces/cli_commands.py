from shutil import copyfile

import click

from tally.config import home_dir, repo_root
from tally.db import init_db


def _not_implemented(command_name: str) -> None:
    click.echo(f"{command_name}: not implemented yet")


@click.command()
def setup() -> None:
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
    _not_implemented("sync")


@click.command()
def status() -> None:
    _not_implemented("status")


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
