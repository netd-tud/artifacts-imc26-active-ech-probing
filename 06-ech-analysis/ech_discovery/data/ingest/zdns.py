from ech_discovery.data.ingest.dataset import Dataset, get_sld
from ech_discovery.data.columns import Columns as C
from loguru import logger
import duckdb


class ZDNSData(Dataset):
    columns = {
        "name": "VARCHAR",
        "results": """
     STRUCT(HTTPS STRUCT("data" STRUCT(additionals STRUCT(flags VARCHAR, "type" VARCHAR, udpsize BIGINT, "version" BIGINT, ede STRUCT(error_text VARCHAR, extra_text VARCHAR, info_code BIGINT)[])[], authorities STRUCT("class" VARCHAR, expire BIGINT, mbox VARCHAR, min_ttl BIGINT, "name" VARCHAR, ns VARCHAR, "refresh" BIGINT, retry BIGINT, serial BIGINT, ttl BIGINT, "type" VARCHAR)[], protocol VARCHAR, resolver VARCHAR, answers STRUCT("class" VARCHAR, "name" VARCHAR, priority BIGINT, svcparams STRUCT(alpn VARCHAR[], ipv4hint VARCHAR[], ipv6hint VARCHAR[], ech VARCHAR), target VARCHAR, ttl BIGINT, "type" VARCHAR)[]), duration DOUBLE, status VARCHAR, "timestamp" TIMESTAMP, error VARCHAR))
    """,
    }

    def _extract_metadata(self):
        self.date = self.src_file.parts[-2]
        self.role = self.src_file.parts[-3]
        self.loc = self.src_file.parts[-4]

    def duckdb_parse(self):
        if self.dst_file.is_file() and not self.force:
            logger.info(f"Skipping file {self.dst_file} because it already exists")
            return

        self.make_dst_file_dir()

        (
            duckdb.read_json(str(self.src_file), columns=self.columns)
            .select(
                f"""
                regexp_replace(regexp_extract(filename, '.*?([^./]+T[^./]*).*', 1), '_', ':', 'g')::TIMESTAMP as measurement,
                name,
                '{self.loc}' AS {C.location},
                '{self.role}' AS {C.role},
                unnest(results, recursive:=true)"""
            )
            .select(
                # Ensure only one entry per domain name. Early versions of the input list included the same name multiple times.
                "*, row_number() OVER (PARTITION BY name ORDER BY timestamp) AS rn"
            )
            .filter("rn = 1")
            .select("* EXCLUDE (rn)")
            .select(
                f"""* EXCLUDE (additionals, authorities, answers), 
                unnest(answers, recursive:=true), 
                unnest(additionals, recursive:=true), 
                unnest(authorities, recursive:=true),
                sld(name) AS "{C.target_sld}"
                """
            )
            .select("*, echme(ech) AS ech_processed")
            .write_parquet(
                str(self.dst_file), compression="zstd", row_group_size=1_000_000, use_tmp_file=True
            )
        )
