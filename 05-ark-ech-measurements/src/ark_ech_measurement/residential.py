from typing import List, Optional
from pathlib import Path
from ark_ech_measurement.util import filter_target_instances_primitive
import typer
import scamper
from loguru import logger
import re
import json
import urllib.request

app = typer.Typer()


def filter_residential(asns: list[int]) -> list[int]:
    residential = []
    for i in range(0, len(asns), 150):
        batch = asns[i : i + 150]
        url = f"https://www.peeringdb.com/api/net?asn__in={','.join(map(str, batch))}&fields=asn,info_type"
        with urllib.request.urlopen(url) as r:
            data = json.load(r).get("data", [])
        residential.extend(
            d["asn"] for d in data if d.get("info_type") == "Cable/DSL/ISP"
        )
    return residential


def get_residential_vantagepoints() -> list[str]:
    with urllib.request.urlopen("https://api.arkmon.caida.org/public/locations") as r:
        mons = json.load(r).get("mons", {})
    return [m["name"] for m in mons.values() if m.get("Class") == "Residential"]


def diff(a: list, b: list) -> list[str]:
    b_names = {item.shortname for item in b}
    return [item.shortname for item in a if item.shortname not in b_names]


@app.command()
def get_nodes(
    primitives: List[str],
    socket: Optional[str] = typer.Option(None, "--socket"),
    mux: Optional[str] = typer.Option(None, "--mux"),
):
    if socket is None and mux is None:
        raise typer.BadParameter("Either --socket or --mux must be provided.")

    ctrl = scamper.ScamperCtrl(unix=socket, mux=mux)

    instances = filter_target_instances_primitive(ctrl, primitives)
    logger.info(f"Found {len(instances)} matching primitives")

    ### ASN filter
    asns = list(map(lambda x: x.asn4, instances)) + list(
        map(lambda x: x.asn6, filter(lambda x: hasattr(x, "asn6"), instances))
    )

    asns = filter_residential(asns)

    logger.info(f"ASNs: {len(instances)}")
    instances_with_asn = []

    for instance in instances:
        if instance.asn4 in asns or hasattr(instance, "asn6") and instance.asn6 in asns:
            instances_with_asn += [instance]

    logger.info(f"Filtered instance count with asn: {len(instances_with_asn)}")
    ### CAIDA residential
    instances_caida = list(
        filter(lambda x: x.shortname in get_residential_vantagepoints(), instances)
    )

    logger.info(f"Filtered instance count (CAIDA): {len(instances_caida)}")

    ### Differences
    print(diff(instances_caida, instances_with_asn))
    print(diff(instances_with_asn, instances_caida))

    final_list = list(map(lambda x: x.shortname, instances_caida))
    typer.echo(final_list)


def _vp_record(vp) -> dict:
    loc = getattr(vp, "loc", None)
    return {
        "source": "ark",
        "name": getattr(vp, "name", None),
        "shortname": getattr(vp, "shortname", None),
        "ipv4": getattr(vp, "ipv4", None),
        "asn4": getattr(vp, "asn4", None),
        "ipv6": getattr(vp, "ipv6", None),
        "asn6": getattr(vp, "asn6", None),
        "cc": getattr(vp, "cc", None),
        "st": getattr(vp, "st", None),
        "place": getattr(vp, "place", None),
        "iata": getattr(vp, "iata", None),
        "loc": list(loc) if loc is not None else None,
        "tags": list(getattr(vp, "tags", None) or []),
    }


def _caida_record(shortname: str, caida: dict) -> dict:
    lat = caida.get("latitude")
    lon = caida.get("longitude")
    return {
        "source": "caida_api",
        "name": caida.get("name"),
        "shortname": shortname,
        "ipv4": None,
        "asn4": caida.get("as_number"),
        "ipv6": None,
        "asn6": None,
        "cc": None,
        "st": None,
        "place": caida.get("city"),
        "iata": None,
        "loc": [lat, lon] if lat is not None and lon is not None else None,
        "tags": [],
        "caida_class": caida.get("Class"),
        "caida_continent": caida.get("Continent"),
        "caida_hardware": caida.get("Hardware"),
        "caida_os": caida.get("Operating System"),
        "caida_activity": caida.get("Activity"),
        "caida_org": caida.get("org_name"),
        "caida_activation": caida.get("activation"),
        "caida_contributed": caida.get("contributed"),
        "caida_ping": caida.get("ping"),
    }


@app.command()
def nodes_meta(
    outfile: Path = typer.Argument(..., help="Output JSONL file path"),
    socket: Optional[str] = typer.Option(None, "--socket"),
    mux: Optional[str] = typer.Option(None, "--mux"),
    instances: Optional[str] = typer.Option(
        None, "--instances", help="Comma-separated list of shortnames to include"
    ),
):
    if socket is None and mux is None:
        raise typer.BadParameter("Either --socket or --mux must be provided.")

    ctrl = scamper.ScamperCtrl(unix=socket, mux=mux)

    all_vps = ctrl.vps()
    if instances is not None:
        target = set(instances.split(","))
        vps = [vp for vp in all_vps if vp.shortname in target]
        found = {vp.shortname for vp in vps}
        missing = target - found
        if missing:
            logger.warning(
                f"{len(missing)} requested nodes not present on ARK, falling back to CAIDA API: {sorted(missing)}"
            )
    else:
        vps = all_vps
        missing = set()
    logger.info(f"Fetching metadata for {len(vps)} VPs")

    caida_by_name: dict = {}
    if missing:
        with urllib.request.urlopen(
            "https://api.arkmon.caida.org/public/locations"
        ) as r:
            mons = json.load(r).get("mons", {})
        caida_by_name = {m["name"]: m for m in mons.values() if "name" in m}

    with open(outfile, "w") as f:
        for vp in vps:
            f.write(json.dumps(_vp_record(vp)) + "\n")
        for shortname in sorted(missing):
            caida = caida_by_name.get(shortname)
            if caida is None:
                logger.warning(f"Node {shortname!r} not found in CAIDA API either")
                continue
            f.write(json.dumps(_caida_record(shortname, caida)) + "\n")

    logger.info(
        f"Wrote {len(vps) + len(missing)} records to {outfile} ({len(missing)} from CAIDA API)"
    )
