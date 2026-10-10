from pathlib import Path

from tqdm.auto import tqdm
import polars as pl

from ech_discovery.data import loaders as loader
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment import ech


def retry_configs_first_seen(file: Path, dst_file: Path):
    """First timestamp each retry_configs value is seen, per role, location and ECH public name."""
    (
        pl.scan_parquet(file)
        .filter(ech.ech_accepted)
        .filter(pl.col(C.ech_public_name).is_not_null())
        .group_by(C.measurement, C.role, C.location, C.ech_public_name, C.retry_configs)
        .agg(pl.col(C.ts).min().alias(C.ts_min))
        .sink_parquet(dst_file)
    )


def aggregate_per_measurement():
    ech_files = loader.FileSelector(globs=[loader.ech_glob]).get_files()
    ech_quic_files = loader.FileSelector(globs=[loader.ech_quic_glob]).get_files()

    for file in tqdm(ech_files + ech_quic_files):
        retry_configs_first_seen(file, file.with_name("retry-configs-first-seen_" + file.name))
