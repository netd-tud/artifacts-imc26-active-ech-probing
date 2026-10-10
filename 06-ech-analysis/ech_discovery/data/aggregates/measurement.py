# Contains all aggregations down to the plain measurement

from pathlib import Path

import polars as pl
from tqdm.auto import tqdm

from ech_discovery import config
from ech_discovery.data import loaders as loader
from ech_discovery.data.aggregates import common
from ech_discovery.data.enrichment import ech
from ech_discovery.data.ranges import TimeRange


def sld_counts(file: Path, dst_file: Path):
    """Number of unique second-level domains that accepted ECH, per role, measurement and location."""
    df = common.without_multi_ech_domains(pl.scan_parquet(file).filter(ech.ech_accepted))
    ech.agg_slds_per_measurement(df).sink_parquet(dst_file)


def aggregate_per_measurement(time_range: TimeRange):
    ech_files = loader.FileSelector(globs=[loader.ech_glob]).get_files()
    ech_quic_files = loader.FileSelector(globs=[loader.ech_quic_glob]).get_files()

    for file in tqdm(common.files_in_range(ech_files + ech_quic_files, time_range)):
        sld_counts(file, file.with_name("sld-count_" + file.name))


def agg_accepted_sld(
    dst_file: Path = config.PROCESSED_DATA_DIR / "accepted_sld.pq.zst",
    dst_file_all_locations: Path = config.PROCESSED_DATA_DIR / "accepted_sld_all_locations.pq.zst",
):
    """Unique domains that accepted ECH via TCP or QUIC, per measurement date and location."""
    common.unique_domains_by_date(ech.ech_accepted, dst_file, dst_file_all_locations)
