from pathlib import Path

import polars as pl
from tqdm.auto import tqdm

from ech_discovery.data import loaders as loader
from ech_discovery.data.aggregates import common
from ech_discovery.data.aggregates.common import cv
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.ranges import TimeRange

DOMAIN_SETS = {
    "follow": "follow-ech-domains",
    "cf_meta": "multi-ech-domains_cloudflare_and_meta",
}

DOMAIN_SET = "domain_set"


def _domain_set_labels() -> pl.DataFrame:
    """`(target, domain_set)` for every domain set, materialised once."""
    return pl.concat(
        [
            cv.load_data(dataset)
            .select(C.target)
            .unique()
            .with_columns(pl.lit(set_name).alias(DOMAIN_SET))
            for set_name, dataset in DOMAIN_SETS.items()
        ]
    ).collect()


def agg_dns_status(time_range: TimeRange, dst_file: Path | None = None):
    """DNS status counts per (measurement, location, status) for each domain set."""
    if dst_file is None:
        dst_file = common.processed_file("dns_status", time_range)

    files = common.files_in_range(
        loader.FileSelector(globs=[loader.zdns_glob]).get_files(), time_range
    )
    labels = _domain_set_labels().lazy()

    dfs = []
    for file in tqdm(files):
        dfs.append(
            pl.scan_parquet(file)
            .filter(time_range.expr())
            .select(C.measurement, C.location, C.status, C.zdns_target)
            .join(
                labels,
                left_on=C.zdns_target,
                right_on=C.target,
                how="inner",
                validate="m:1",
            )
            .group_by(C.measurement, C.location, C.status, DOMAIN_SET)
            .agg(pl.col(C.zdns_target).drop_nulls().n_unique().alias(C.len))
            .collect()
        )
    cv.write_parquet(pl.concat(dfs), dst_file)
