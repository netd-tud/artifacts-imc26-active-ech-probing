from pathlib import Path

import polars as pl
import polars.selectors as cs

from ech_discovery import config
from ech_discovery.data.aggregates.common import cv
from ech_discovery.data.columns import Columns as C

_PHASE_TIMESTAMPS = cs.matches("^.*(tls|hdr|data).*(tx|rx)$")

_PHASE_LIST_COLS = [
    "tls",
    "hdr",
    "ech_tls",
    "ech_hdr",
    "ech_data",
    "grease_tls",
    "grease_hdr",
    "grease_data",
]


def _ms(duration: pl.Expr) -> pl.Expr:
    return duration.dt.total_microseconds() / 10**3


def load_ark_rtt() -> pl.LazyFrame:
    """Ark probe results with per-phase RTT columns (ms) derived from the tx/rx timestamps."""
    files = list(sorted((config.PROCESSED_DATA_DIR / "ark").glob("*/*.pq.zst")))
    return (
        pl.scan_parquet(
            files,
            include_file_paths=C.measurement,
        )
        .with_columns(
            pl.coalesce(pl.col("^.*inst$")).alias("vp"),
            pl.col(C.measurement)
            .str.split("/")
            .list.get(-2)
            .str.replace_all("_", ":")
            .str.to_datetime("%+"),
            _ms(pl.col("ech_hsrtt", "hsrtt").str.to_time().cast(pl.Duration)),
            cs.matches("^dns_.*(tx|rx)$").str.to_datetime("%+"),
            (_PHASE_TIMESTAMPS & cs.list(cs.string())).list.eval(
                pl.element().str.to_datetime("%+")
            ),
        )
        .with_columns(
            # Ensure values with null are also cast to list(datetime)
            _PHASE_TIMESTAMPS.cast(pl.List(pl.Datetime(time_zone="UTC")))
        )
        .with_columns(
            # Single value column: duration calculation
            _ms(pl.col(f"{col}_rx") - pl.col(f"{col}_tx")).alias(f"{col}_rtt")
            for col in ["dns_HTTPS_dns", "dns_A_dns"]
        )
        .with_columns(
            # List columns: duration calculation
            *(
                _ms(pl.col(f"{col}_rx").list.min() - pl.col(f"{col}_tx").list.min()).alias(
                    f"{col}_min_rtt"
                )
                for col in _PHASE_LIST_COLS
            ),
            *(
                _ms(pl.col(f"{col}_rx").list.max() - pl.col(f"{col}_tx").list.min()).alias(
                    f"{col}_max_rtt"
                )
                for col in _PHASE_LIST_COLS
            ),
        )
        .with_columns(
            (pl.col("ech_tls_max_rtt") - pl.col("tls_max_rtt")).alias("ech_minus_tls_rtt"),
            (pl.col("ech_tls_max_rtt") - pl.col("grease_tls_max_rtt")).alias(
                "ech_minus_grease_tls_rtt"
            ),
        )
    )


def agg_ark_timing(
    dst_file: Path = config.PROCESSED_DATA_DIR / "ark_timing.pq.zst",
):
    """Median ECH-vs-TLS RTT difference per public-name group, plus the measurement span."""
    base = load_ark_rtt()

    groups = {
        "cloudflare": pl.col("ech_ech_outer_sni") == config.PUBLIC_NAME_CLOUDFLARE,
        "meta": pl.col("ech_ech_outer_sni") == config.PUBLIC_NAME_META,
        "main": pl.col("ech_ech_outer_sni").is_in(config.MAIN_ECH_PUBLIC_NAMES),
        "all": pl.lit(True),
    }
    dfs = [
        base.filter(fltr).select(
            pl.lit(name).alias("group"),
            pl.col("ech_minus_tls_rtt").median().alias("median_ech_minus_tls_rtt"),
            pl.len(),
            pl.col(C.measurement).min().alias("measurement_min"),
            pl.col(C.measurement).max().alias("measurement_max"),
        )
        for name, fltr in groups.items()
    ]
    cv.sink_parquet(pl.concat(dfs), dst_file)
