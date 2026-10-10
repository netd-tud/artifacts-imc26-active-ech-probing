import typer
import scamper
from collections import deque
from typing import List, Optional, Annotated
from ark_ech_measurement.util import (
    filter_target_instances,
    get_target_from_measurement,
)
import csv
from .ECHMeasurements import ECHMeasurements
from pathlib import Path
from loguru import logger
from .ECHMeasurementPipeline import ECHMeasurementPipeline
from datetime import timedelta

app = typer.Typer()


@app.command()
def admit_domains(
    pending: deque,
    active: set,
    pipelines: dict,
    ctrl: scamper.ScamperCtrl,
    window_size: int,
):
    while len(active) < window_size and pending:
        row = pending.popleft()
        domain = row["target"]
        url = row["url"] if "url" in row else None
        active.add(domain)
        for inst in ctrl.instances():
            pipeline = ECHMeasurementPipeline(domain, url, inst, ctrl)
            pipelines[(domain, inst.shortname)] = pipeline
            pipeline.start()


@app.command()
def file(
    file: Annotated[typer.FileText, typer.Argument()],
    socket: Optional[str] = typer.Option(None, "--socket"),
    mux: Optional[str] = typer.Option(None, "--mux"),
    outfile: Annotated[
        Path | None,
        typer.Option(exists=False, file_okay=True, dir_okay=False, writable=True),
    ] = None,
    instances: str = typer.Option(
        ["hlz2-nz"], help="Comma-separated list of instances, e.g. a,b,c"
    ),
    window_size: int = typer.Option(50, "--window-size"),
):
    if socket is None and mux is None:
        raise typer.BadParameter("Either --socket or --mux must be provided.")

    scamper_outfile = None
    if outfile is not None:
        scamper_outfile = scamper.ScamperFile(str(outfile), "w")

    ctrl = scamper.ScamperCtrl(unix=socket, outfile=scamper_outfile, mux=mux)
    target_instances = filter_target_instances(ctrl, instances)
    ctrl.add_vps(target_instances)
    instance_names = [i.shortname for i in ctrl.instances()]
    logger.info(f"Target instances {len(target_instances)}")

    pending: deque = deque(csv.DictReader(file))
    active: set = set()
    pipelines: dict[tuple[str, str], ECHMeasurementPipeline] = {}

    admit_domains(pending, active, pipelines, ctrl, window_size)

    while active:
        try:
            o = ctrl.poll(timeout=timedelta(seconds=5))
        except Exception as e:
            logger.error(f"poll error: {e}")
            continue

        if o is None:
            if ctrl.is_done():
                logger.info("all measurements complete")
                break
            stuck = [(k, p.stage, p) for k, p in pipelines.items() if not p.done]
            for s in stuck:
                s[-1].done = True
                active.discard(s[-1].domain)
            admit_domains(pending, active, pipelines, ctrl, window_size)
            logger.warning(
                f"poll timed out with active domains still in flight ({len(stuck)}): {stuck[:10]}"
            )
            continue

        domain = get_target_from_measurement(o)
        if domain is None:
            logger.warning(f"could not extract domain from response: {o}")
            continue

        key = (domain, o.inst.shortname)
        pipeline = pipelines.get(key)
        if pipeline is None:
            logger.warning(f"no pipeline found for {key}")
            continue

        try:
            pipeline.advance(o)
        except Exception as e:
            logger.error(f"pipeline error for {key}: {e}")
            pipeline.done = True  # avoid hanging the window slot

        if pipeline.done:
            if all(p.done for (d, _), p in pipelines.items() if d == domain):
                active.discard(domain)
                admit_domains(pending, active, pipelines, ctrl, window_size)
                logger.info(
                    f"VP done: {domain} on {o.inst.shortname}, stage: {pipeline.stage}"
                )
                logger.info(
                    f"domain complete: {domain}, active: {len(active)}, pending: {len(pending)}"
                )
            else:
                logger.info(
                    f"VP done: {domain} on {o.inst.shortname}, stage: {pipeline.stage} waiting for remaining VPs"
                )

    if scamper_outfile is not None:
        scamper_outfile.close()
