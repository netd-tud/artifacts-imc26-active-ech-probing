from datetime import date
from os import path
from pathlib import Path
from typing import List, Union
import polars as pl
from ech_discovery import config
from ech_discovery.data.columns import Columns as C
import ech_discovery.data.enrichment.ech as _ech
import ech_discovery.data.enrichment.zdns as _zdns
import re

import ndpi

import ndpi.convenience as cv  # noqa: E402, F401

# Glob patterns for the interim datasets, relative to config.INTERIM_DATA_DIR
zdns_glob = "ech-zdns/*/20*.pq.zst"
ech_glob = "ech/*/20*.pq.zst"
ech_quic_glob = "ech-quic/*/20*.pq.zst"
cert_ech_glob = "cert-ech/*/20*.pq.zst"
cert_ech_quic_glob = "cert-ech-quic/*/20*.pq.zst"

ech_error_glob = "ech/*/errors_20*.pq.zst"
ech_quic_error_glob = "ech-quic/*/errors_20*.pq.zst"

ech_input_glob = "ech/*/input_20*.pq.zst"
ech_quic_input_glob = "ech-quic/*/input_20*.pq.zst"

ech_input_stats_glob = "ech/*/input_stats_20*.pq.zst"
ech_quic_input_stats_glob = "ech-quic/*/input_stats_20*.pq.zst"

# Per-measurement aggregate outputs written next to the interim files
stats_glob = "*/*/stats_20*.pq.zst"
latency_stats_glob = "*/*/latency-stats_20*.pq.zst"
meas_duration_glob = "*/*/meas-duration_20*.pq.zst"
sld_count_glob = "*/*/sld-count_20*.pq.zst"
total_stats_glob = "ech/*/total_stats_20*.pq.zst"
total_stats_all_locations_glob = "ech/*/total_stats_all_locations_20*.pq.zst"
retry_configs_first_seen_glob = "*/*/retry-configs-first-seen_20*.pq.zst"


class FileSelector:
    def __init__(
        self,
        globs: List[str],
        regex_filter: str = "",
        limit: int = 0,
        limit_per_location: bool = False,
        from_begin: bool = False,
        dir=config.INTERIM_DATA_DIR,
        loc_pos=-2,
    ) -> None:
        self.globs = globs
        self.regex_filter = regex_filter
        self.limit = limit
        self.from_begin = from_begin
        self.dir = dir
        # Position in the path to find location
        self.loc_pos = loc_pos
        self.limit_per_location = limit_per_location

        self._resolve_glob()
        self._filter_files()
        self._apply_file_limits()

    def get_files(self):
        return sorted(self.files)

    def _resolve_glob(self):
        self.files = []
        for glob in self.globs:
            self.files += self.dir.glob(glob)

        self.files = list(set(self.files))

    def _regex_filter(self, file: Union[Path, str]) -> bool:
        return bool(re.search(self.regex_filter, str(file)))

    def _filter_files(self):
        self.files = list(filter(self._regex_filter, self.files))

    def _get_locations(self):
        return list(set(map(lambda x: x.parts[self.loc_pos], self.files)))

    def _apply_file_limits(self):
        if self.limit_per_location:
            locations = self._get_locations()
            new_files = []
            for loc in locations:
                files_from_loc = list(filter(lambda x: x.parts[self.loc_pos] == loc, self.files))
                new_files.extend(_get_files(sorted(files_from_loc), self.limit, self.from_begin))
            self.files = new_files
        else:
            self.files = _get_files(sorted(self.files), self.limit, self.from_begin)


def _get_files(files, limit=0, from_begin=False):
    if from_begin:
        return files[:limit]
    return files[-limit:]


def scan(globs, filter: pl.Expr = pl.lit(True), **selector_kwargs) -> pl.LazyFrame:
    return pl.scan_parquet(FileSelector(globs=globs, **selector_kwargs).get_files()).filter(filter)


def without_multi_ech_domains(df: pl.LazyFrame, as_of: date | None = None) -> pl.LazyFrame:
    """Drop domains that showed up with both a Cloudflare and a Meta public name."""
    multi_ech = cv.load_data("multi-ech-domains_cloudflare_and_meta")
    if as_of is not None:
        multi_ech = multi_ech.filter(pl.col(C.measurement).dt.date() <= as_of)
    return df.join(multi_ech, on=C.target, how="anti").filter(
        ~pl.col(C.target_sld).is_in(config.MULTI_ECH_EXCLUDED_SLDS)
    )


def ech_tcp_tls(
    filter: pl.Expr = _ech.ech_accepted,
    globs: List[str] = [ech_glob],
    filter_multi_ech: bool = True,
    **selector_kwargs,
) -> pl.LazyFrame:
    df = scan(globs, filter, **selector_kwargs)
    return without_multi_ech_domains(df) if filter_multi_ech else df


def ech_quic(
    filter: pl.Expr = _ech.ech_accepted,
    globs: List[str] = [ech_quic_glob],
    filter_multi_ech: bool = True,
    **selector_kwargs,
) -> pl.LazyFrame:
    df = scan(globs, filter, **selector_kwargs)
    return without_multi_ech_domains(df) if filter_multi_ech else df


def cert_ech_tcp_tls(
    filter: pl.Expr = _ech.ech_accepted,
    globs: List[str] = [cert_ech_glob],
    filter_multi_ech: bool = True,
    **selector_kwargs,
) -> pl.LazyFrame:
    df = scan(globs, filter, **selector_kwargs)
    return without_multi_ech_domains(df) if filter_multi_ech else df


def cert_ech_quic(
    filter: pl.Expr = _ech.ech_accepted,
    globs: List[str] = [cert_ech_quic_glob],
    filter_multi_ech: bool = True,
    **selector_kwargs,
) -> pl.LazyFrame:
    df = scan(globs, filter, **selector_kwargs)
    return without_multi_ech_domains(df) if filter_multi_ech else df


def ech(
    filter: pl.Expr = _ech.ech_accepted,
    globs: List[str] | None = None,
    filter_multi_ech: bool = True,
    **selector_kwargs,
) -> pl.LazyFrame:
    return pl.concat(
        [
            ech_tcp_tls(filter, globs or [ech_glob], filter_multi_ech, **selector_kwargs),
            ech_quic(filter, globs or [ech_quic_glob], filter_multi_ech, **selector_kwargs),
        ]
    )


def ech_input(
    filter: pl.Expr = pl.lit(True),
    globs: List[str] = [ech_quic_input_glob, ech_input_glob],
    filter_multi_ech: bool = True,
    **selector_kwargs,
) -> pl.LazyFrame:
    df = scan(globs, filter, **selector_kwargs)
    return without_multi_ech_domains(df) if filter_multi_ech else df


def ech_input_stats(
    filter: pl.Expr = pl.lit(True),
    globs: List[str] = [ech_quic_input_stats_glob, ech_input_stats_glob],
    **selector_kwargs,
) -> pl.LazyFrame:
    return scan(globs, filter, **selector_kwargs)


def ech_error_stats(
    filter: pl.Expr = pl.lit(True),
    globs: List[str] = [ech_quic_error_glob, ech_error_glob],
    **selector_kwargs,
) -> pl.LazyFrame:
    return scan(globs, filter, **selector_kwargs)


def zdns(
    filter: pl.Expr = _zdns.ech_field, globs: List[str] = [zdns_glob], **selector_kwargs
) -> pl.LazyFrame:
    return scan(globs, filter, **selector_kwargs)


def ech_stats(
    filter: pl.Expr = pl.lit(True), globs: List[str] = [stats_glob], **selector_kwargs
) -> pl.LazyFrame:
    """Domains per public name for connections that accepted ECH."""
    return scan(globs, filter, **selector_kwargs).filter(pl.col(C.kind) == "accepted")


def ech_failed_stats(
    filter: pl.Expr = pl.lit(True), globs: List[str] = [stats_glob], **selector_kwargs
) -> pl.LazyFrame:
    """Domains per public name where ECH failed although a retry config was offered."""
    return (
        scan(globs, filter, **selector_kwargs)
        .filter(pl.col(C.kind) == "failed_retry")
        .rename({C.target_sld: C.target_sld_failed})
    )


def ech_latency_stats(
    filter: pl.Expr = pl.lit(True), globs: List[str] = [latency_stats_glob], **selector_kwargs
) -> pl.LazyFrame:
    return scan(globs, filter, **selector_kwargs)


def ech_measurement_durations(
    filter: pl.Expr = pl.lit(True), globs: List[str] = [meas_duration_glob], **selector_kwargs
) -> pl.LazyFrame:
    """Measurement duration per role, measurement and location, over all connections."""
    return scan(globs, filter, **selector_kwargs)


def ech_sld_counts(
    filter: pl.Expr = pl.lit(True), globs: List[str] = [sld_count_glob], **selector_kwargs
) -> pl.LazyFrame:
    """Number of unique SLDs that accepted ECH, per role, measurement and location."""
    return scan(globs, filter, **selector_kwargs)


def ech_total_stats(
    filter: pl.Expr = pl.lit(True), globs: List[str] = [total_stats_glob], **selector_kwargs
) -> pl.LazyFrame:
    return scan(globs, filter, **selector_kwargs)


def ech_total_stats_all_locations(
    filter: pl.Expr = pl.lit(True),
    globs: List[str] = [total_stats_all_locations_glob],
    **selector_kwargs,
) -> pl.LazyFrame:
    """Domains per public name over the union of every location measured that day."""
    return scan(globs, filter, **selector_kwargs)


def ech_retry_configs_first_seen(
    filter: pl.Expr = pl.lit(True),
    globs: List[str] = [retry_configs_first_seen_glob],
    **selector_kwargs,
) -> pl.LazyFrame:
    """Per-measurement (role, location, ech_public_name, retry_configs) -> first ts_min in that file."""
    return scan(globs, filter, **selector_kwargs)
