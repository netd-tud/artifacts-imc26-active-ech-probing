from pathlib import Path

from ech_discovery.data.ingest.dataset import Dataset, get_sld
import duckdb
from loguru import logger

from ech_discovery.data.columns import Columns as C
import polars as pl

from ech_discovery import config


def _cv():
    import ndpi

    import ndpi.convenience as cv

    return cv


ECH_SUCCESSFUL = "ECH Successful"
ECH_SUCCESSFUL_IN_DNS = "ECH with Configuration in DNS"
ECH_SUCCESSFUL_NO_DNS = "ECH without Configuration in DNS"

error_mapping = {
    " tls: ": "TLS Error",
    "127.0.0.1:53": "Name Resolution Failure",
    "context deadline exceeded": "Connection Timeout",
    " i/o timeout": "Connection Timeout",
    "empty RetryConfigs": "ECH Unsupported",
    "retry config len: 0": "ECH Unsupported",
    "tcp": "TCP Error",
    None: ECH_SUCCESSFUL,
}


def with_error_reason(df):
    """Extract the raw error-reason string (the `error_mapping` key) from the error column.

    The first matching key in `error_mapping` wins, independent of where it occurs in the
    error string.
    """
    keys = [key for key in error_mapping if key is not None]
    reason = pl.when(pl.col(C.error).str.contains(keys[0], literal=True)).then(pl.lit(keys[0]))
    for key in keys[1:]:
        reason = reason.when(pl.col(C.error).str.contains(key, literal=True)).then(pl.lit(key))
    return df.with_columns(reason.otherwise(None).alias(C.error_reason)).with_columns(
        pl.coalesce(C.error_reason, C.error).alias(C.error_reason)
    )


def split_success_by_ech_in_dns(df, label_col: str = C.label, ech_in_dns_col: str | None = None):
    """Replace the success label in `label_col` by ECH with DNS and without config in DNS"""
    if ech_in_dns_col is None:
        from ech_discovery.data.mapper import Strings

        ech_in_dns_col = str(Strings.ech_in_dns)

    is_success = pl.col(label_col).is_null() | (pl.col(label_col) == ECH_SUCCESSFUL)
    in_dns = pl.col(ech_in_dns_col).fill_null(False)
    return df.with_columns(
        pl.when(is_success & in_dns)
        .then(pl.lit(ECH_SUCCESSFUL_IN_DNS))
        .when(is_success)
        .then(pl.lit(ECH_SUCCESSFUL_NO_DNS))
        .otherwise(pl.col(label_col))
        .alias(label_col)
    )


class ECHData(Dataset):
    columns = {
        "domain": "VARCHAR",
        "ip": "VARCHAR",
        "data": """
     STRUCT(ech STRUCT(status VARCHAR, protocol VARCHAR, result STRUCT(
     "timestamp" VARCHAR,
     target VARCHAR, 
     protocol VARCHAR, 
     port USMALLINT, 
     conn_primer VARCHAR, 
     conn_primer_failed BOOLEAN,
     error VARCHAR, 
     failed_connection_attempts USMALLINT,
     retry_configs_failed_connection_attempts USMALLINT,
     anchor_failed_connection_attempts USMALLINT,
     ech_version USMALLINT, 
     ech_config_id UTINYINT,
     ech_public_name VARCHAR, 
     ech_kem_name USMALLINT,
     ech_config_len USMALLINT,
     ech_cipher_suites VARCHAR[],
     ech_max_name_len UTINYINT,
     ech_raw_extensions VARCHAR,
     alpn_list JSON[],
     ipv4_hints JSON[],
     ipv6_hints JSON[],
     ip VARCHAR,
     transport VARCHAR,
     tls_version VARCHAR,
     tls_handshake_duration_with_ech BIGINT,
     tls_handshake_duration_without_ech BIGINT,
     tls_handshake_anchor_ip VARCHAR,
     accepted_ech BOOLEAN,
     tls_handshake_completed BOOLEAN,
     ttfb BIGINT, 
     anchor_ttfb BIGINT,
     negotiated_protocol VARCHAR,
     negotiated_cipher VARCHAR,
     retry_configs STRUCT(
     ech_version USMALLINT,
     ech_config_id UTINYINT,
     ech_public_name VARCHAR,
     ech_public_key VARCHAR,
     ech_cipher_suites VARCHAR[],
     ech_max_name_len UTINYINT
     )[], client_hello_outer STRUCT(
     original JSON,
     vers BIGINT,
     random VARCHAR,
     session_id VARCHAR,
     cipher_suites BIGINT[],
     compression_methods VARCHAR,
     server_name VARCHAR,
     ocsp_stampling BOOLEAN,
     supported_curves BIGINT[],
     supported_points JSON,
     ticket_supported BOOLEAN,
     session_ticket JSON,
     supported_signature_algorithms BIGINT[],
     supported_signature_algorithms_cert JSON,
     secure_renegotation_supported BOOLEAN,
     secure_renegotation JSON,
     extended_master_secret BOOLEAN,
     alpn_protocols VARCHAR[],
     scts BOOLEAN,
     supported_versions BIGINT[], 
     early_data BOOLEAN,
     psk_modes JSON,
     psk_binders JSON, 
     quic_transport_parameters JSON,
     encrypted_client_hello JSON),
     client_hello_inner STRUCT(original JSON,
     vers BIGINT,
     random VARCHAR,
     session_id VARCHAR,
     cipher_suites BIGINT[],
     compression_methods VARCHAR,
     server_name VARCHAR,
     ocsp_stampling BOOLEAN,
     supported_curves BIGINT[],
     supported_points JSON,
     ticket_supported BOOLEAN,
     session_ticket JSON,
     supported_signature_algorithms BIGINT[],
     supported_signature_algorithms_cert JSON,
     secure_renegotation_supported BOOLEAN,
     secure_renegotation JSON,
     extended_master_secret BOOLEAN,
     alpn_protocols VARCHAR[],
     scts BOOLEAN,
     supported_versions BIGINT[],
     early_data BOOLEAN,
     psk_modes JSON, 
     psk_binders JSON, 
     quic_transport_parameters JSON, 
     encrypted_client_hello JSON), 
     server_hello STRUCT(original VARCHAR,
     vers BIGINT,
     random VARCHAR,
     session_id VARCHAR,
     cipher_suite BIGINT,
     compression_method BIGINT,
     ocsp_stampling BOOLEAN, 
     ticket_supported BOOLEAN,
     secure_renegotation_supported BOOLEAN,
     secure_renegotiation JSON,
     extended_master_secrete BOOLEAN, 
     alpn_protocol VARCHAR, 
     scts JSON, 
     supported_version BIGINT,
     selected_identity_present BOOLEAN,
     selected_identity BIGINT,
     supported_points JSON,
     encrypted_client_hello JSON,
     server_name_ack BOOLEAN,
     selected_group BIGINT))[],
     "timestamp" TIMESTAMP))
    """,
    }

    def _extract_metadata(self):
        self.date = self.src_file.parts[-3]
        self.role = self.src_file.parts[-4]
        self.loc = self.src_file.parts[-5]

    def aggregate_errors(self):
        dst_file = Path(str(self.dst_file).replace(f"{self.loc}/", f"{self.loc}/errors_"))
        if dst_file.is_file() and not self.force:
            logger.info(f"Skipping file {dst_file} because it already exists")
            return

        _cv().sink_parquet(
            pl.scan_parquet(self.dst_file)
            .pipe(with_error_reason)
            .group_by(C.measurement, C.role, C.location, C.target_sld, C.error_reason)
            .agg(pl.col(C.target).n_unique().alias(C.len)),
            dst_file,
        )

    def duckdb_parse(self):
        if not self.dst_file.is_file() or self.force:
            self.make_dst_file_dir()

            duckdb.read_json(str(self.src_file), columns=self.columns, records="true").select(
                "regexp_replace(regexp_extract(filename, '.*?([^./]+T[^./]*).*', 1), '_', ':', 'g')::TIMESTAMP as measurement, unnest(data, recursive:=true), domain"
            ).select(
                "* EXCLUDE (result, timestamp, protocol), unnest(result) as result, timestamp AS outer_ts, protocol AS outer_protocol"
            ).select("* EXCLUDE (result, domain), unnest(result)").select(
                f"* EXCLUDE(timestamp), timestamp::TIMESTAMP as timestamp, sld(target) AS \"{C.target_sld}\", '{self.role}' AS {C.role}, '{self.loc}' AS {C.location}",
            ).query(
                "r",
                # Ensure only one entry per domain name. Early versions of the input list included the same name multiple times.
                f"SELECT * FROM r QUALIFY row_number() OVER (PARTITION BY {C.target} ORDER BY {C.ts}) = 1",
            ).order("accepted_ech, ech_public_name").write_parquet(
                str(self.dst_file), compression="zstd", row_group_size=1_000_000, use_tmp_file=True
            )
        else:
            logger.info(f"Skipping file {self.dst_file} because it already exists")

        self.aggregate_errors()


class ECHInputData(ECHData):
    def _set_dst_file(self):
        self.dst_file = self.dst_dir / self.role / self.loc / f"input_{self.date}.pq.zst"

    def polars_parse(self):
        cv = _cv()
        cv.sink_parquet(
            pl.scan_csv(self.src_file, has_header=False, new_columns=[C.target]).with_columns(
                pl.lit(self.role).alias(C.role),
                pl.lit(self.date).str.replace("_", ":").cast(pl.Datetime).alias(C.measurement),
                pl.lit(self.loc).alias(C.location),
                pl.col(C.target).map_elements(get_sld, return_dtype=pl.String).alias(C.target_sld),
            ),
            self.dst_file,
        )
        cv.sink_parquet(
            pl.scan_parquet(self.dst_file)
            .group_by(C.measurement, C.role, C.location)
            .agg(
                pl.col(C.target_sld).n_unique().alias(C.target_sld_total),
                pl.col(C.target).n_unique().alias(C.target_total),
            ),
            Path(str(self.dst_file).replace("input_", "input_stats_")),
        )

    def duckdb_parse(self):
        self.polars_parse()
