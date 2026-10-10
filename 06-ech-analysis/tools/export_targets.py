#!/usr/bin/env python3
"""Export domain target lists for the one-off measurements (zgrab2 TLS-version probing,
NS/A-record CDN checks, echtool grace-period/configuration-variations), all consistently
scoped to a single chosen measurement --date so results stay comparable across measurements.

Each subcommand prints one domain per line to stdout by default (so it can be piped straight
into zdns/zgrab2, matching the existing manual convention), or to --output if given. Every
subcommand also accepts --criteria-file to additionally write a small JSON record of exactly
what was queried, so raw output is traceable back to the parameters that produced it.

Usage:
    uv run python tools/export_targets.py sample --date 2026-07-11
    uv run python tools/export_targets.py cf-meta --date 2026-07-11 | tools/zdns/zdns NS
    uv run python tools/export_targets.py all-input --date 2026-07-11 | tools/zdns/zdns A
    uv run python tools/export_targets.py cf-quic-only --date 2026-07-11 | ./tools/zgrab2 tls ...
"""

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import sys

import polars as pl

from ech_discovery import config
from ech_discovery.data import loaders as loader
from ech_discovery.data.aggregates.common import cv, processed_file
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment import ech
from ech_discovery.data.loaders import without_multi_ech_domains
from ech_discovery.data.ranges import ALL, FOLLOWUP, MAIN

RANGES = {"main": MAIN, "followup": FOLLOWUP, "all": ALL}

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T\d{2}_\d{2}_\d{2}\+\d{2}_\d{2}")


def _extract_date_from_name(filename: str) -> date | None:
    """Extract the measurement date from a filename regardless of prefix (e.g. `input_...`,
    which breaks `aggregates.common.extract_date`'s isoformat parsing)."""
    m = _DATE_RE.search(filename)
    return date.fromisoformat(m.group(1)) if m else None


def _write_criteria(criteria_file: Path | None, criteria: dict) -> None:
    if criteria_file is None:
        return
    criteria = {**criteria, "generated_at": datetime.now(timezone.utc).isoformat()}
    criteria_file.parent.mkdir(parents=True, exist_ok=True)
    criteria_file.write_text(json.dumps(criteria, indent=2, default=str) + "\n")
    print(f"criteria written to {criteria_file}", file=sys.stderr)


def _write_domains(domains: list[str], output: Path | None) -> None:
    text = "\n".join(domains) + ("\n" if domains else "")
    if output is None:
        sys.stdout.write(text)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text)
        print(f"{len(domains)} domains written to {output}", file=sys.stderr)


def cmd_cf_meta(args: argparse.Namespace) -> None:
    target_date = date.fromisoformat(args.date)
    domains = (
        cv.load_data("multi-ech-domains_cloudflare_and_meta")
        .filter(pl.col(C.measurement).dt.date() <= target_date)
        .select(C.target)
        .drop_nulls()
        .unique()
        .sort(C.target)
        .collect()[C.target]
        .to_list()
    )
    _write_domains(domains, args.output)
    _write_criteria(
        args.criteria_file,
        {"date": args.date, "source": "multi-ech-domains_cloudflare_and_meta", "count": len(domains)},
    )


def cmd_all_input(args: argparse.Namespace) -> None:
    target_date = date.fromisoformat(args.date)
    # Resolve the date from filenames, not by scanning row data: concatenating all 239
    # ech_input/ech_quic_input files and reducing on a data column overflows polars' default
    # 32-bit row index ("Polars' maximum length reached") well before any filter can narrow it
    # down -- so only ever scan the file(s) for the exact requested date.
    files = loader.FileSelector(globs=[loader.ech_input_glob, loader.ech_quic_input_glob]).get_files()
    dated = [(d, f) for f in files if (d := _extract_date_from_name(f.name)) is not None]
    use_files = [f for d, f in dated if d == target_date]
    if not use_files:
        available = sorted({d for d, _ in dated})
        raise SystemExit(
            f"no ech_input/ech_quic_input data for exactly {target_date}. "
            f"Nearest available dates: {[str(d) for d in available if d <= target_date][-3:]} "
            f"(before) / {[str(d) for d in available if d > target_date][:3]} (after)."
        )
    domains = (
        pl.scan_parquet(use_files)
        .select(C.target)
        .drop_nulls()
        .unique()
        .sort(C.target)
        .collect()[C.target]
        .to_list()
    )
    _write_domains(domains, args.output)
    _write_criteria(
        args.criteria_file,
        {
            "date": args.date,
            "source": "ech_input (ech_input_glob + ech_quic_input_glob)",
            "count": len(domains),
        },
    )


def cmd_cf_quic_only(args: argparse.Namespace) -> None:
    target_date = date.fromisoformat(args.date)
    time_range = RANGES[args.range]
    # quic_only_domains only carries target-sld (no full `target` domain), unlike the
    # notebook-only file this replaces (07-quic-only-domains-cloudflare.ipynb) which had a real
    # `target` column -- SLDs are used here since that's what the pipeline aggregate produces.
    domains = (
        pl.scan_parquet(processed_file("quic_only_domains", time_range))
        .filter(
            pl.col(C.ech_public_name) == config.PUBLIC_NAME_CLOUDFLARE,
            pl.col(C.location) == "tud",
            pl.col(C.measurement).dt.date() == target_date,
        )
        .select(C.target_sld)
        .drop_nulls()
        .unique()
        .sort(C.target_sld)
        .collect()[C.target_sld]
        .to_list()
    )
    _write_domains(domains, args.output)
    _write_criteria(
        args.criteria_file,
        {
            "date": args.date,
            "range": args.range,
            "source": f"quic_only_domains_{args.range}",
            "note": "target-sld, not full target -- see script comment",
            "count": len(domains),
        },
    )


def cmd_sample(args: argparse.Namespace) -> None:
    target_date = date.fromisoformat(args.date)
    date_str = args.date
    per_public_name = args.per_public_name

    ech_files = loader.FileSelector(
        globs=[loader.ech_glob], regex_filter=f"tud.*{date_str}"
    ).get_files()
    quic_files = loader.FileSelector(
        globs=[loader.ech_quic_glob], regex_filter=f"tud.*{date_str}"
    ).get_files()
    if not ech_files or not quic_files:
        raise SystemExit(
            f"no same-day tud ech ({len(ech_files)} files) + ech-quic ({len(quic_files)} "
            f"files) data for {target_date} -- pick a date where both exist"
        )

    df = without_multi_ech_domains(
        pl.scan_parquet(ech_files + quic_files).filter(ech.ech_accepted), as_of=target_date
    ).select(C.ech_public_name, C.target_sld, C.target)

    per_sld = df.unique(subset=[C.ech_public_name, C.target_sld], keep="first")

    sampled = (
        per_sld.with_columns((pl.col(C.target_sld) + pl.lit(date_str)).hash(seed=0).alias("_rank"))
        .sort([C.ech_public_name, "_rank"])
        .with_columns(pl.int_range(pl.len()).over(C.ech_public_name).alias("_idx"))
        .filter(pl.col("_idx") < per_public_name)
        .drop("_rank", "_idx")
        .collect()
    )

    out_dir = config.RAW_DATA_DIR / "tud" / "echtool" / "targets" / date_str
    if args.tag:
        # Keep the untagged path (consumed by `make measure-targets` and downstream
        # echtool/grace-period/configuration-variations Make targets) stable; a --tag lands
        # in its own subdirectory so e.g. a larger Ark sample doesn't clobber it.
        out_dir = out_dir / args.tag
    targets = sorted(sampled[C.target].unique().to_list())
    _write_domains(targets, out_dir / "targets.txt")

    manifest = sampled.select(
        C.target, C.target_sld, C.ech_public_name
    ).with_columns(pl.lit(date_str).alias("sample_date")).sort(C.ech_public_name, C.target)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest.write_csv(out_dir / "domains.csv")
    print(f"{manifest.height} domains written to {out_dir / 'domains.csv'}", file=sys.stderr)

    _write_criteria(
        out_dir / "criteria.json",
        {
            "date": date_str,
            "per_public_name_limit": per_public_name,
            "ech_source_files": [f.name for f in ech_files],
            "ech_quic_source_files": [f.name for f in quic_files],
            "total_domains": len(targets),
            "total_public_names": sampled[C.ech_public_name].n_unique(),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--date", required=True, help="YYYY-MM-DD, shared across all measurements")
        p.add_argument("--output", type=Path, help="Write domains here instead of stdout")
        p.add_argument("--criteria-file", type=Path, help="Also write a JSON criteria record here")

    p_cf_meta = sub.add_parser("cf-meta", help="Cloudflare+Meta multi-CDN domains, up to --date")
    add_common(p_cf_meta)
    p_cf_meta.set_defaults(func=cmd_cf_meta)

    p_all_input = sub.add_parser("all-input", help="All probed domains, as of --date")
    add_common(p_all_input)
    p_all_input.set_defaults(func=cmd_all_input)

    p_quic = sub.add_parser("cf-quic-only", help="Cloudflare QUIC-only domains, on --date")
    add_common(p_quic)
    p_quic.add_argument("--range", choices=RANGES, default="all")
    p_quic.set_defaults(func=cmd_cf_quic_only)

    p_sample = sub.add_parser(
        "sample", help="Sample up to N domains/ECH public name, from --date's same-day tud data"
    )
    p_sample.add_argument("--date", required=True, help="YYYY-MM-DD; tud must have same-day ech+ech-quic")
    p_sample.add_argument("--per-public-name", type=int, default=50)
    p_sample.add_argument(
        "--tag",
        help=(
            "Write to targets/<date>/<tag>/ instead of targets/<date>/, so a second sample "
            "for the same date (e.g. a larger Ark run) doesn't overwrite the default one "
            "that `make measure-targets` and the echtool Make targets read from"
        ),
    )
    p_sample.set_defaults(func=cmd_sample)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
