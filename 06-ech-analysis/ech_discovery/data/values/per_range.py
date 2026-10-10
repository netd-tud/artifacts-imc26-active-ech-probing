from datetime import date
from pathlib import Path
import re

from ndpi.value_store import ValueStore, fmt_date, fmt_eng, fmt_percent
import polars as pl

from ech_discovery import config
from ech_discovery.data import loaders as loader
from ech_discovery.data.aggregates import common
from ech_discovery.data.aggregates.common import cv, processed_file
from ech_discovery.data.aggregates.public_names import _closest_quic_files
from ech_discovery.data.columns import Columns as C
from ech_discovery.data.enrichment import ech
from ech_discovery.data.enrichment.ech import is_example_public_name, is_nordvpn_target
from ech_discovery.data.mapper import Strings
from ech_discovery.data.metrics import common as metrics_common
from ech_discovery.data.metrics import locations as metrics_locations
from ech_discovery.data.ranges import TimeRange, follow_domain_date
from ech_discovery.data.values.common import (
    Key,
    and_join,
    key_fn,
    measurement_location,
    name_part,
    pct_label,
    roles,
)

pct = fmt_percent(digits=0)
dfmt = fmt_date("%b %-d, %Y")

# Columns of the one-row frame `_dns_status_counts` returns.
_TOTAL = "total"
_IN_DNS = "in-dns"
_NO_DNS = "no-dns"
_IN_DNS_SHARE = "in-dns [%]"
_NO_DNS_SHARE = "no-dns [%]"

# HPKE identifiers (RFC 9180): KEM ids as echtool reports them, and the value-name
# spelling of the KDF/AEAD parts of a cipher suite string.
HPKE_KEM_NAMES = {
    16: "DHKEM(P-256, HKDF-SHA256)",
    17: "DHKEM(P-384, HKDF-SHA384)",
    18: "DHKEM(P-521, HKDF-SHA512)",
    32: "DHKEM(X25519, HKDF-SHA256)",
    33: "DHKEM(X448, HKDF-SHA512)",
}
HPKE_KDF_KEYS = {"SHA256": "Sha256", "SHA384": "Sha384", "SHA512": "Sha512"}
HPKE_AEAD_KEYS = {
    "AES128GCM": "Aes128Gcm",
    "AES256GCM": "Aes256Gcm",
    "CHACHA20POLY1305": "ChaCha20Poly1305",
}
_CIPHER_SUITE_RE = re.compile(r"kdf: (?P<kdf>[^,]+), aead: (?P<aead>[^}]+)")


def eng(x: float) -> str | int:
    return fmt_eng(places=1)(x) if x >= 1000 else round(x)


def _latest_accepted(
    time_range: TimeRange, locations: list[str] | None = None
) -> tuple[pl.LazyFrame, Path]:
    """ECH-accepting rows of the latest snapshot in `time_range`, and the file they are keyed to."""
    selector = loader.FileSelector(globs=[loader.ech_glob], regex_filter=measurement_location)
    files = common.files_in_range(selector.get_files(), time_range)
    file_ech = max(files, key=common.extract_date)
    df = common.without_multi_ech_domains(
        pl.scan_parquet([file_ech] + _closest_quic_files(file_ech, locations)).filter(
            ech.ech_accepted
        )
    )
    return df, file_ech


def latest_public_name_targets(
    fltr: list[pl.Expr], time_range: TimeRange, col=C.target
) -> pl.LazyFrame:
    df, _ = _latest_accepted(time_range, locations=[measurement_location])
    return df.filter(fltr).select(pl.col(col).drop_nulls().n_unique())


def _asn_shares(time_range: TimeRange, location: str, agg_col: str) -> pl.LazyFrame:
    error_asn = metrics_common.latest(
        pl.scan_parquet(config.PROCESSED_DATA_DIR / "follow_error_asn.pq.zst"),
        time_range,
        location,
    )
    return (
        error_asn.group_by(C.error_reason, pl.col(agg_col).fill_null("unresolved"))
        .agg(pl.col(C.len).sum())
        .with_columns(
            (100 * pl.col(C.len) / pl.col(C.len).sum().over(C.error_reason)).alias(C.len_percent)
        )
    )


def _measurement_date(latency: pl.LazyFrame, time_range: TimeRange) -> date:
    """Last day a measurement actually ran within `time_range`, at the reference location."""
    return (
        latency.filter(pl.col(C.location) == measurement_location, time_range.expr())
        .select(pl.col(C.measurement).max())
        .collect()
        .item()
        .date()
    )


def register_for_range(
    store: ValueStore,
    time_range: TimeRange,
    stats: pl.LazyFrame,
    total_stats: pl.LazyFrame,
    total_stats_all_locations: pl.LazyFrame,
    latency: pl.LazyFrame,
) -> None:
    """Register every value that depends on `time_range`, keyed under its range prefix."""
    md = _measurement_date(latency, time_range)

    key = key_fn(time_range)

    store.register(key("echMeasurementDate"), md, fmt=dfmt)
    _register_public_names(store, key, time_range, stats, total_stats, total_stats_all_locations)
    _register_dns_status(store, key, time_range)
    _register_hpke(store, key, time_range)
    _register_consistency(store, key, time_range, md, total_stats_all_locations)
    _register_cf_meta(store, key, time_range, md)
    _register_latency(store, key, time_range, latency)
    _register_measurement_spans(store, key, time_range, latency)
    _register_domains_per_location(store, key, time_range)


def _total_domains_max(
    total_stats: pl.LazyFrame, time_range: TimeRange, public_name: str
) -> pl.LazyFrame:
    """Peak per-measurement total within `time_range`, not just the last snapshot."""
    return (
        total_stats.filter(pl.col(C.ech_public_name) == public_name, time_range.expr())
        .group_by(C.measurement)
        .agg(pl.col(C.target_sld).sum())
        .select(pl.col(C.target_sld).max())
    )


def _register_public_names(
    store: ValueStore,
    key: Key,
    time_range: TimeRange,
    stats: pl.LazyFrame,
    total_stats: pl.LazyFrame,
    total_stats_all_locations: pl.LazyFrame,
) -> None:
    """Domains per ECH deployment, and the shape of the Cloudflare/Meta/nordvpn ones."""

    def latest(df: pl.LazyFrame) -> pl.LazyFrame:
        return metrics_common.latest(df, time_range, measurement_location)

    def total_domains(public_name: str) -> pl.LazyFrame:
        return metrics_common.latest_of(
            total_stats.filter(pl.col(C.ech_public_name) == public_name), time_range
        ).select(pl.col(C.target_sld).sum())

    for ech_public_name, name in [
        (config.PUBLIC_NAME_CLOUDFLARE, "cloudflare"),
        (config.PUBLIC_NAME_META, "meta"),
    ]:
        store.register(
            key(f"{name}EchDomainsTotalLast"),
            total_domains(ech_public_name),
            fmt=eng,
        )
        store.register(
            key(f"{name}EchDomainsTotalMax"),
            _total_domains_max(total_stats_all_locations, time_range, ech_public_name),
            fmt=eng,
        )
        for role, role_name in [("ech", "Ech"), ("ech-quic", "EchQuic")]:
            role_last = latest(
                stats.filter(
                    pl.col(C.ech_public_name) == ech_public_name,
                    pl.col(C.role) == role,
                )
            )
            store.register(
                key(f"{name}{role_name}DomainsLast"),
                role_last.select(pl.col(C.target_sld).sum()),
                fmt=eng,
            )
            if ech_public_name == config.PUBLIC_NAME_CLOUDFLARE:
                store.register(
                    key(f"{name}{role_name}DomainsShareNoDnsLast"),
                    role_last.select(
                        pl.col(C.target_sld).filter(~pl.col(Strings.ech_in_dns)).sum()
                        / pl.col(C.target_sld).sum()
                        * 100
                    ),
                    fmt=pct,
                )
    cf_quic_only = pl.scan_parquet(processed_file("quic_only_domains", time_range)).filter(
        pl.col(C.ech_public_name) == config.PUBLIC_NAME_CLOUDFLARE
    )
    cf_quic_only_tud = latest(cf_quic_only)
    store.register(
        key("cloudflareEchQuicOnlyTudLast"),
        cf_quic_only_tud.select(pl.col(C.target_sld).drop_nulls().n_unique()),
        fmt=eng,
    )
    store.register(
        key("cloudflareEchQuicOnlyRuTudLast"),
        cf_quic_only_tud.select(
            pl.col(C.target_sld).filter(pl.col("tld") == "ru").drop_nulls().n_unique()
            / pl.col(C.target_sld).drop_nulls().n_unique()
            * 100
        ),
        fmt=pct,
    )
    store.register(
        key("metaEchDomainsSubdomainsFbsbxLast"),
        metrics_common.latest(
            pl.scan_parquet(processed_file("meta_fbsbx_domains", time_range)),
            time_range,
            measurement_location,
        ).select(
            pl.col(C.target_sld).filter(pl.col("fbsbx")).sum() / pl.col(C.target_sld).sum() * 100
        ),
        fmt=pct,
    )

    store.register(
        key("echPublicNameTotalExampleLast"),
        # Unique generated *.example.com ECH public names at the latest snapshot in the range.
        metrics_common.latest_of(total_stats, time_range).select(
            pl.col(C.ech_public_name).filter(is_example_public_name()).drop_nulls().n_unique()
        ),
        fmt=eng,
    )

    store.register(
        key("echPublicNameTotalTargetDomainsExampleLast"),
        latest_public_name_targets(
            [
                is_example_public_name(),
                is_nordvpn_target(),
            ],
            time_range,
            col=C.target,
        ),
        fmt=eng,
    )
    store.register(
        key("echPublicNameTotalTargetSndDomainsExampleLast"),
        latest_public_name_targets(
            [
                is_example_public_name(),
                is_nordvpn_target(),
            ],
            time_range,
            col=C.target_sld,
        ),
        fmt=eng,
    )


def _dns_status_counts(time_range: TimeRange, col: str) -> pl.LazyFrame:
    """Distinct `col` values accepting ECH at the latest tud snapshot, split by ECH in DNS."""
    df, file_ech = _latest_accepted(time_range, locations=[measurement_location])
    per_domain = (
        common.with_ech_in_dns(df, file_ech, on=col)
        .group_by(col)
        .agg(pl.col(Strings.ech_in_dns).any())
    )
    in_dns = pl.col(Strings.ech_in_dns).sum()
    return per_domain.select(
        pl.len().alias(_TOTAL),
        in_dns.alias(_IN_DNS),
        (pl.len() - in_dns).alias(_NO_DNS),
        (in_dns / pl.len() * 100).alias(_IN_DNS_SHARE),
        (100 - in_dns / pl.len() * 100).alias(_NO_DNS_SHARE),
    )


def _register_dns_status(store: ValueStore, key: Key, time_range: TimeRange) -> None:
    """How many ECH-accepting domains announce ECH in DNS as well, per SLD and per queried name."""
    for col, name in [(C.target_sld, "Sld"), (C.target, "Target")]:
        counts = _dns_status_counts(time_range, col)
        store.register(key(f"echAccepted{name}TotalLast"), counts.select(_TOTAL), fmt=eng)
        store.register(key(f"echAccepted{name}InDnsLast"), counts.select(_IN_DNS), fmt=eng)
        store.register(key(f"echAccepted{name}NoDnsLast"), counts.select(_NO_DNS), fmt=eng)
        store.register(
            key(f"echAccepted{name}InDnsShareLast"), counts.select(_IN_DNS_SHARE), fmt=pct
        )
        store.register(
            key(f"echAccepted{name}NoDnsShareLast"), counts.select(_NO_DNS_SHARE), fmt=pct
        )


def _hpke_key(name: str, known: dict[str, str]) -> str:
    return known.get(name, re.sub(r"[^A-Za-z0-9]", "", name).capitalize())


def _cipher_suite_key(suite: str) -> str:
    """Value-name suffix for a cipher suite as echtool prints it, e.g. `Sha256Aes128Gcm`."""
    match = _CIPHER_SUITE_RE.search(suite)
    if match is None:
        return re.sub(r"[^A-Za-z0-9]", "", suite).capitalize()
    return _hpke_key(match["kdf"], HPKE_KDF_KEYS) + _hpke_key(match["aead"], HPKE_AEAD_KEYS)


def _register_hpke(store: ValueStore, key: Key, time_range: TimeRange) -> None:
    """KEM and cipher suites the ECH configurations of accepting domains offer."""
    df, _ = _latest_accepted(time_range, locations=[measurement_location])
    store.register(
        key("echKemSharesLast"),
        df.group_by(C.ech_kem_name)
        .agg(pl.col(C.target_sld).drop_nulls().n_unique())
        .join(df.select(pl.col(C.target_sld).drop_nulls().n_unique().alias("total")), how="cross")
        .with_columns((pl.col(C.target_sld) / pl.col("total") * 100).alias(C.len_percent))
        .sort(C.len_percent, descending=True)
        .select(
            pct_label(
                pl.col(C.ech_kem_name)
                .replace_strict(
                    HPKE_KEM_NAMES,
                    default=pl.col(C.ech_kem_name).cast(pl.String),
                    return_dtype=pl.String,
                )
                .fill_null("unknown")
            ).alias("label")
        )
        .pipe(and_join),
    )

    # Collected here because the suites present in the data decide the value names.
    per_suite = (
        df.select(C.target_sld, C.retry_configs)
        .explode(C.retry_configs)
        .select(C.target_sld, pl.col(C.retry_configs).struct.field(C.ech_cipher_suites))
        .explode(C.ech_cipher_suites)
        .drop_nulls(C.ech_cipher_suites)
        .group_by(C.ech_cipher_suites)
        .agg(pl.col(C.target_sld).drop_nulls().n_unique())
        .join(df.select(pl.col(C.target_sld).drop_nulls().n_unique().alias("total")), how="cross")
        .sort([C.target_sld, C.ech_cipher_suites], descending=[True, False])
        .collect()
    )
    for rank, (suite, domains, total) in enumerate(per_suite.iter_rows()):
        suite_key = _cipher_suite_key(suite)
        store.register(key(f"echCipherSuite{suite_key}SldLast"), domains, fmt=eng)
        if rank == 0:
            store.register(
                key(f"echCipherSuite{suite_key}MissingSldLast"), total - domains, fmt=eng
            )


def _register_consistency(
    store: ValueStore,
    key: Key,
    time_range: TimeRange,
    md: date,
    total_stats_all_locations: pl.LazyFrame,
) -> None:
    """How consistently domains still support ECH at the end of the measurement."""

    def err_share(group: pl.Expr) -> pl.LazyFrame:
        """Share of followed domains matching `group`, among all followed-domain error reasons."""
        err_stats = metrics_common.latest(
            pl.scan_parquet(
                config.PROCESSED_DATA_DIR / "error_statistics_followed_domains.pq.zst"
            ),
            time_range,
            measurement_location,
        )
        return err_stats.select(
            pl.col(C.target).filter(group).sum() / pl.col(C.target).sum() * 100
        )

    store.register(
        key("echSupportEndOfMeasurementLast"),
        err_share(pl.col(C.error_reason).is_null()),
        fmt=pct,
    )
    store.register(
        key("echSupportEndOfMeasurementNXDomainLast"),
        err_share(pl.col(C.error_reason) == "127.0.0.1:53"),
        fmt=pct,
    )
    store.register(
        key("echSupportEndOfMeasurementRetryEmptyLast"),
        err_share(pl.col(C.error_reason) == "empty RetryConfigs"),
        fmt=pct,
    )
    store.register(key("echSupportEndOfMeasurementDuration"), (md - follow_domain_date).days)

    store.register(
        key("echSupportEndOfMeasurementHostingAsTypeLast"),
        _asn_shares(time_range, measurement_location, "asn-type")
        .filter(
            pl.col("asn-type") == "hosting",
            pl.col(C.error_reason) == "empty RetryConfigs",
            pl.col(C.len) == pl.col(C.len).max().over(C.error_reason),
        )
        .select(C.len_percent),
        fmt=pct,
    )
    store.register(
        key("echSupportEndOfMeasurementHostingAsPrimaryLast"),
        _asn_shares(time_range, measurement_location, "asn-name")
        .filter(pl.col(C.error_reason) == "empty RetryConfigs")
        .top_k(2, by=C.len_percent)
        .sort(C.len_percent, descending=True)
        .select(
            pct_label(
                pl.col("asn-name").str.split(" ").list.get(0).str.split(".").list.get(0)
            ).alias("label")
        )
        .pipe(and_join),
        note="renamed from echSupoprtEndOfMeasurementHostingAsPrimary",
    )

    store.register(
        key("echDomainsWoCfMetaMax"),
        _total_domains_max(
            total_stats_all_locations, time_range, config.PUBLIC_NAME_NOT_CLOUDFLARE_META
        ),
        fmt=eng,
    )

    store.register(
        key("echAnonymitySetSizeWoMetaCloudflareMax"),
        total_stats_all_locations.filter(
            ~pl.col(C.ech_public_name).is_in(config.MAIN_ECH_PUBLIC_NAMES_ALL),
            pl.col(C.ech_public_name) != config.PUBLIC_NAME_NOT_CLOUDFLARE_META,
            time_range.expr(),
        )
        .group_by(C.ech_public_name, C.measurement)
        .agg(pl.col(C.target_sld).sum())
        .select(pl.col(C.target_sld).max()),
    )

    store.register(
        key("echFailAfterProvidingRetryLast"),
        metrics_common.latest(
            pl.scan_parquet(config.PROCESSED_DATA_DIR / "retry_provided.pq.zst"),
            time_range,
            measurement_location,
        ).select(pl.col(C.target_sld)),
        fmt=eng,
    )


def _register_cf_meta(store: ValueStore, key: Key, time_range: TimeRange, md: date) -> None:
    """The domain set seen under both a Cloudflare and a Meta public name."""

    def cf_meta() -> pl.LazyFrame:
        return cv.load_data("multi-ech-domains_cloudflare_and_meta").filter(
            pl.col(C.measurement).dt.date() <= md
        )

    def cf_meta_tld_share(tld: str) -> pl.LazyFrame:
        cf_meta_tlds = (
            cf_meta()
            .group_by(pl.col(C.target).str.split(".").list.get(-1))
            .agg(pl.len())
            .with_columns((pl.col(C.len) / pl.col(C.len).sum() * 100).alias(C.len_percent))
        )
        return cf_meta_tlds.filter(pl.col(C.target) == tld).select(C.len_percent)

    store.register(key("cloudflareAndMetaDomainsTotal"), cf_meta().select(pl.len()), fmt=eng)
    store.register(key("cloudflareAndMetaDomainsCom"), cf_meta_tld_share("com"), fmt=pct)
    store.register(key("cloudflareAndMetaDomainsCn"), cf_meta_tld_share("cn"), fmt=pct)
    store.register(
        key("cloudflareAndMetaDomainsRedirectShare"),
        cf_meta()
        .group_by(pl.col(C.target).str.contains("redirect"))
        .agg(pl.len())
        .with_columns((pl.col(C.len) / pl.col(C.len).sum() * 100).alias(C.len_percent))
        .filter(pl.col(C.target))
        .select(C.len_percent),
        fmt=pct,
    )
    store.register(
        key("cloudflareAndMetaDomainsNXDOMAINLast"),
        metrics_common.latest(
            pl.scan_parquet(processed_file("dns_status", time_range)),
            time_range,
            measurement_location,
        )
        .filter(pl.col("domain_set") == "cf_meta", pl.col(C.status) == "NXDOMAIN")
        .select(pl.col(C.len).sum()),
    )


def _register_latency(
    store: ValueStore, key: Key, time_range: TimeRange, latency: pl.LazyFrame
) -> None:
    """TLS handshake latency with and without ECH, and the accepted-domain totals behind it."""
    latency_ech_tud = metrics_common.latest(
        latency.filter(pl.col(C.role) == "ech"), time_range, measurement_location
    )
    store.register(
        key("tlsLatencyMedianTudLast"),
        latency_ech_tud.select(pl.col(C.hs_duration_without_ech + "-median")),
        fmt=eng,
    )
    store.register(
        key("tlsLatencyMeanTudLast"),
        latency_ech_tud.select(pl.col(C.hs_duration_without_ech + "-mean")),
        fmt=eng,
    )
    store.register(
        key("tlsLatencyPenaltyMedianTudLast"),
        latency_ech_tud.select(pl.col(C.hs_duration_diff + "-median")),
        fmt=".1f",
    )
    store.register(
        key("tlsLatencyPenaltyMedianShareTudLast"),
        latency_ech_tud.select(
            pl.col(C.hs_duration_diff + "-median")
            / pl.col(C.hs_duration_without_ech + "-median")
            * 100
        ),
        fmt=pct,
    )
    store.register(
        key("echAcceptedSldLast"),
        metrics_common.latest(
            pl.scan_parquet(config.PROCESSED_DATA_DIR / "accepted_sld.pq.zst"),
            time_range,
            measurement_location,
        ).select(pl.col(C.target_sld)),
        fmt=eng,
    )
    store.register(
        key("echAcceptedTargetMax"),
        pl.scan_parquet(config.PROCESSED_DATA_DIR / "accepted_sld_all_locations.pq.zst")
        .filter(time_range.expr())
        .select(pl.col(C.target).max()),
        fmt=eng,
    )


def _register_measurement_spans(
    store: ValueStore, key: Key, time_range: TimeRange, latency: pl.LazyFrame
) -> None:
    """Start, end and count of the measurement runs per role, plus the cloud run date."""

    def _measurement_span(role: str) -> dict[str, pl.LazyFrame]:
        role_meas = latency.filter(
            pl.col(C.role) == role,
            pl.col(C.location) == measurement_location,
            time_range.expr(),
        )
        return {
            "start": role_meas.select(pl.col(C.measurement).min()),
            "end": role_meas.select(pl.col(C.measurement).max()),
            "count": role_meas.select(C.measurement).unique().select(pl.len()),
        }

    def _cloud_measurement_max(role: str) -> pl.LazyFrame:
        return (
            latency.filter(
                pl.col(C.role) == role,
                pl.col(C.location) != measurement_location,
                time_range.expr(),
            )
            .select(C.location, C.measurement)
            .unique()
            .group_by(C.location)
            .agg(pl.len())
            .select(pl.col(C.len).max())
        )

    def _cloud_measurement_date(role: str) -> pl.LazyFrame:
        """Last day any cloud vantage point ran."""
        return latency.filter(
            pl.col(C.role) == role,
            pl.col(C.location) != measurement_location,
            time_range.expr(),
        ).select(pl.col(C.measurement).max())

    for role_key, role in roles.items():
        span = _measurement_span(role)
        store.register(key(f"measurement{role_key}StartDate"), span["start"], fmt=dfmt)
        store.register(key(f"measurement{role_key}EndDate"), span["end"], fmt=dfmt)
        store.register(key(f"measurement{role_key}StartMonthDay"), span["start"], fmt="%b %-d")
        store.register(key(f"measurement{role_key}EndMonthDay"), span["end"], fmt="%b %-d")
        store.register(key(f"measurementCount{role_key}"), span["count"])
        store.register(key(f"measurementCount{role_key}CloudMax"), _cloud_measurement_max(role))
        store.register(
            key(f"measurement{role_key}CloudDate"), _cloud_measurement_date(role), fmt=dfmt
        )


def _excluded_label(excluded: list[str]) -> str:
    """The `location (reason)` entries as prose, or `none` when nothing was left out."""
    joined = pl.Series("label", excluded, dtype=pl.String).to_frame().pipe(and_join).item()
    return joined or "none"


def _register_domains_per_location(store: ValueStore, key: Key, time_range: TimeRange) -> None:
    """Cross-location spread of accepted domains, per location set and role, and what it
    leaves out - one pair of values per transport, with and without the primary location."""
    spread = metrics_locations.domains_per_location_spread(time_range, measurement_location)
    for row in spread.iter_rows(named=True):
        name = (
            "domainsPerLocation"
            + name_part(row[metrics_locations.LOCATION_SET])
            + name_part(row[C.role])
        )
        dates = ", ".join(str(day) for day in row[metrics_locations.MEASUREMENT_DATES])
        store.register(
            key(f"{name}MaxDiffPct"),
            row[metrics_locations.MAX_DIFF_PCT],
            fmt=fmt_percent(digits=1),
            note=f"measured {dates}",
        )
        store.register(key(f"{name}Excluded"), _excluded_label(row[metrics_locations.EXCLUDED]))
