import json
from typing import Annotated
import scamper
import typer
import csv
from .ECHParser import read_file
import polars as pl

app = typer.Typer()


@app.command()
def cli(
    file: Annotated[str, typer.FileBinaryRead],
    parquet: Annotated[str | None, typer.FileBinaryWrite] = None,
):
    results = read_file(file)

    if parquet is not None:
        pl.LazyFrame(
            list(results.values()),
            schema_overrides={
                "dns_HTTPS_dns_rx": pl.String,
                "dns_HTTPS_dns_tx": pl.String,
            },
            infer_schema_length=None,
        ).sink_parquet(parquet)
        return

    print(json.dumps(results))
