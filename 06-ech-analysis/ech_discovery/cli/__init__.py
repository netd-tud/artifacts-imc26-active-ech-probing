import click

from ech_discovery.cli.aggregate import aggregate
from ech_discovery.cli.ingest import ingest
from ech_discovery.cli.values import values


@click.group()
def cli():
    pass


cli.add_command(ingest)
cli.add_command(aggregate)
cli.add_command(values)


if __name__ == "__main__":
    cli()
