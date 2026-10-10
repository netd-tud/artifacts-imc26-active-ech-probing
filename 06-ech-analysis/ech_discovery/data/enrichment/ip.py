import polars as pl

from ech_discovery import config
from ech_discovery.data.columns import Columns as C

LOCATION_MMDB = config.EXTERNAL_DATA_DIR / "ipinfo" / "ipinfo_location-2026-08-07.mmdb"
LOCATION_PARQUET = config.EXTERNAL_DATA_DIR / "ipinfo" / "ipinfo_location-2026-08-07.parquet"
ASN_MMDB = config.EXTERNAL_DATA_DIR / "ipinfo" / "ipinfo_asn-2026-08-07.mmdb"

ASIA = "Asia"


def country_continent() -> pl.LazyFrame:
    """Country code -> continent, as ipinfo itself labels them in the location database.

    The mmdb is IP-keyed and only the parquet release can be read country-first, so this
    reads that instead of `LOCATION_MMDB`. Both come from the same ipinfo snapshot.
    """
    return (
        pl.scan_parquet(LOCATION_PARQUET)
        .select(pl.col("country_code").alias(C.country), C.continent)
        .unique()
    )


def ip_lookup(df, col=C.ipv4_addresses):
    """Lookup table of the unique IPs in `col` with continent/country/ASN columns."""
    import maxminddb

    location = maxminddb.open_database(LOCATION_MMDB)
    asn = maxminddb.open_database(ASN_MMDB)

    ip_addresses = (
        df.select(pl.col(col))
        .unique()
        .with_columns(
            pl.col(col)
            .map_elements(
                lambda x: (location.get(x) or {}).get("continent"), return_dtype=pl.String
            )
            .alias(C.continent),
            pl.col(col)
            .map_elements(
                lambda x: (location.get(x) or {}).get("country_code"), return_dtype=pl.String
            )
            .alias(C.country),
            pl.col(col)
            .map_elements(lambda x: (asn.get(x) or {}).get("asn"), return_dtype=pl.String)
            .alias(C.asn),
            pl.col(col)
            .map_elements(lambda x: (asn.get(x) or {}).get("country"), return_dtype=pl.String)
            .alias(C.asn_country),
            pl.col(col)
            .map_elements(lambda x: (asn.get(x) or {}).get("name"), return_dtype=pl.String)
            .alias(C.asn_name),
            pl.col(col)
            .map_elements(lambda x: (asn.get(x) or {}).get("type"), return_dtype=pl.String)
            .alias(C.asn_type),
        )
    )
    return ip_addresses
