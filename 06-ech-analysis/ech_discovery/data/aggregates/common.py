from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from loguru import logger
import polars as pl
from tqdm.auto import tqdm

from ech_discovery import config
from ech_discovery.data import loaders as loader
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment import ech
from ech_discovery.data.mapper import Strings
from ech_discovery.data.ranges import TimeRange

import ndpi

import ndpi.convenience as cv  # noqa: E402, F401


def processed_file(name: str, time_range: TimeRange) -> Path:
    return config.PROCESSED_DATA_DIR / f"{name}_{time_range.name}.pq.zst"


def extract_date(file: Path) -> datetime:
    return datetime.fromisoformat(file.parts[-1].replace(".pq.zst", "").replace("_", ":"))


def extract_location(file: Path) -> str:
    """Vantage point a measurement file was captured at (its parent directory).

    Same convention as `loader.FileSelector`'s default `loc_pos`.
    """
    return file.parts[-2]


def files_in_range(files: list[Path], time_range: TimeRange) -> list[Path]:
    return [f for f in files if time_range.contains(extract_date(f))]


INPUT_LIST_CUTOFF = timedelta(hours=4, minutes=30)


def input_list_day(measurement: datetime) -> date:
    """Day of the input list a run used: the list is regenerated daily at 04:30."""
    return (measurement - INPUT_LIST_CUTOFF).date()


def _day_offset(
    measurement: datetime, file: Path, direction: Literal["any", "backward", "forward"]
) -> timedelta | None:
    """Whole input-list days from `measurement` to `file`, or None if on the wrong side."""
    if direction == "any":
        return timedelta(0)
    offset = input_list_day(extract_date(file)) - input_list_day(measurement)
    if direction == "backward":
        return -offset if offset <= timedelta(0) else None
    return offset if offset >= timedelta(0) else None


def get_closest(
    date: datetime,
    list_of_filenames: list[Path],
    maxdiff=timedelta(days=5),
    direction: Literal["any", "backward", "forward"] = "any",
) -> Path | None:
    """Closest file to `date`, preferring the nearest input-list day allowed by `direction`."""
    ranked = []
    for file in list_of_filenames:
        distance = abs(date - extract_date(file))
        if distance >= maxdiff:
            continue
        offset = _day_offset(date, file, direction)
        if offset is None:
            continue
        ranked.append(((offset, distance), file))
    if not ranked:
        return None
    return min(ranked, key=lambda entry: entry[0])[1]


without_multi_ech_domains = loader.without_multi_ech_domains


ZDNS_JOIN_KEYS = {C.target_sld: C.target_sld, C.target: C.zdns_target}


def with_ech_in_dns(df: pl.LazyFrame, file: Path, on: str = C.target_sld) -> pl.LazyFrame:
    """Add `ECH in DNS` to every row of `df`, from the zdns snapshot closest to `file`.

    `on` picks the granularity: per SLD (any name under it announced ECH) or per queried name
    (`C.target`). Names the snapshot doesn't cover -- and every name, if there is no snapshot
    close enough -- count as False.
    """
    location = extract_location(file)
    zdns_files = [
        f
        for f in loader.FileSelector(globs=[loader.zdns_glob]).get_files()
        if extract_location(f) == location
    ]
    closest = get_closest(extract_date(file), zdns_files, direction="forward")
    if closest is None:
        logger.warning(
            f"No zdns measurement of {location} close to {file}, ECH-in-DNS set to False"
        )
        return df.with_columns(pl.lit(False).alias(Strings.ech_in_dns))

    flags = (
        pl.scan_parquet(closest)
        .group_by(pl.col(ZDNS_JOIN_KEYS[on]).alias(on))
        .agg(pl.col(C.ech).is_not_null().any().alias(Strings.ech_in_dns))
    )
    return df.join(flags, on=on, how="left", validate="m:1").with_columns(
        pl.col(Strings.ech_in_dns).fill_null(False)
    )


def unique_domains_by_date(fltr: pl.Expr, dst_file: Path, dst_file_all_locations: Path) -> None:
    """Unique target names and SLDs matching `fltr`, per measurement date and location.

    Each TCP run is counted together with the closest QUIC run before it at the same location.
    """
    files = loader.FileSelector(globs=[loader.ech_glob]).get_files()

    quic_files: dict[str, list[Path]] = {}
    for quic_file in loader.FileSelector(globs=[loader.ech_quic_glob]).get_files():
        quic_files.setdefault(extract_location(quic_file), []).append(quic_file)

    dfs = []
    for file in tqdm(files):
        location = extract_location(file)
        closest_quic = get_closest(
            extract_date(file), quic_files.get(location, []), direction="backward"
        )
        paired = [file] if closest_quic is None else [file, closest_quic]
        dfs.append(
            without_multi_ech_domains(pl.scan_parquet(paired).filter(fltr))
            .select(
                pl.lit(extract_date(file).date()).alias(C.measurement),
                pl.lit(location).alias(C.location),
                C.target_sld,
                C.target,
            )
            .unique()
            .collect()
        )

    counts = (
        pl.col(C.target_sld).drop_nulls().n_unique(),
        pl.col(C.target).drop_nulls().n_unique(),
    )
    rows = pl.concat(dfs).lazy()
    rows.group_by(C.measurement, C.location).agg(*counts).collect().write_parquet(dst_file)
    rows.group_by(C.measurement).agg(*counts).collect().write_parquet(dst_file_all_locations)


def ech_with_dns_status(
    filter: pl.Expr = ech.ech_accepted,
    globs: list[str] | None = None,
    filter_multi_ech: bool = True,
    **selector_kwargs,
) -> pl.LazyFrame:
    """`loader.ech`-like scan, with the ECH-in-DNS flag joined onto every row."""
    tcp_tls_files = loader.FileSelector(
        globs=globs or [loader.ech_glob], **selector_kwargs
    ).get_files()
    quic_files = loader.FileSelector(
        globs=globs or [loader.ech_quic_glob], **selector_kwargs
    ).get_files()
    frames = []
    for file in tcp_tls_files + quic_files:
        df = pl.scan_parquet(file).filter(filter)
        if filter_multi_ech:
            df = without_multi_ech_domains(df)
        frames.append(with_ech_in_dns(df, file))
    return pl.concat(frames)
