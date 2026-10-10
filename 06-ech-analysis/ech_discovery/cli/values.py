from pathlib import Path

import click

import ech_discovery.config as config


@click.group()
def values():
    pass


@values.command()
@click.option(
    "--path",
    type=click.Path(path_type=Path),
    default=config.REPORTS_DIR / "values.tex",
    show_default=True,
)
def generate(path: Path):
    """Write the paper numbers as \\setval commands (read via \\getval), for every
    range in data.values.RANGES_FOR_VALUES (main and followup)."""
    from ech_discovery.data.values import create_tex_commands

    create_tex_commands(path)
