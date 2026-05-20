import click

from tally.logging_setup import setup_logging
from tally.scheduler import run_scheduler
from tally.surfaces import cli_commands

setup_logging()


class OrderedGroup(click.Group):
    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self.commands)


@click.group(cls=OrderedGroup)
def cli() -> None:
    pass


cli.add_command(cli_commands.setup)
cli.add_command(cli_commands.sync)
cli.add_command(cli_commands.status)
cli.add_command(cli_commands.brief)
cli.add_command(cli_commands.receipt)
cli.add_command(cli_commands.ask)


@cli.command()
def scheduler() -> None:
    run_scheduler()


cli.add_command(cli_commands.facts)
cli.add_command(cli_commands.why)
