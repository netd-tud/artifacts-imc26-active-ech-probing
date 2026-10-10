from os import close
from typing import List, Optional, Annotated
from ark_ech_measurement.util import filter_target_instances
import scamper
import typer
import csv
from .ECHMeasurements import ECHMeasurements
from pathlib import Path
from loguru import logger
from functools import partial
from concurrent.futures import ThreadPoolExecutor, as_completed
from .measure_async import file
from .residential import get_nodes, nodes_meta


app = typer.Typer()

app.command()(file)
app.command()(get_nodes)
app.command()(nodes_meta)


@app.command()
def domain(
    hostname: str,
    url: None | str = None,
    ech_config_list: str = typer.Option(
        None, "--ecl", help="base64 encoded ECH configuration list"
    ),
    socket: Optional[str] = typer.Option(None, "--socket"),
    mux: Optional[str] = typer.Option(None, "--mux"),
    outfile: Annotated[
        Path | None,
        typer.Option(exists=False, file_okay=True, dir_okay=False, writable=True),
    ] = None,
    instances: str = typer.Option(
        [None], help="Comma-separated list of instances, e.g. a,b,c"
    ),
):
    if socket is None and mux is None:
        raise typer.BadParameter("Either --socket or --mux must be provided.")

    if outfile is not None:
        outfile = scamper.ScamperFile(str(outfile), "w")
    ctrl = scamper.ScamperCtrl(unix=socket, outfile=outfile, mux=mux)

    target_instances = filter_target_instances(ctrl, instances)
    ctrl.add_vps(target_instances)
    measurements = ECHMeasurements(ctrl)
    results = {}
    for instance in ctrl.instances():
        logger.info(f"Running on instance {instance.shortname}")
        results[instance] = measurements.measure_target(
            hostname, url, ech_config_list, instance=instance, sync=True
        )
    typer.echo(results)
    if outfile is not None:
        outfile.close()


if __name__ == "__main__":
    app()
