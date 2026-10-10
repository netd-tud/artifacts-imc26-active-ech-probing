from abc import ABC, abstractmethod
from functools import lru_cache
import json
import os
from pathlib import Path
from typing import List, Type
from ech_discovery import config
import duckdb
import subprocess

from publicsuffixlist import PublicSuffixList


class Dataset(ABC):
    def __init__(self, path: Path, dst_dir: Path = config.INTERIM_DATA_DIR, force: bool = False):
        self.force = force
        self.src_file = path
        self.dst_dir = dst_dir
        self._extract_metadata()
        self._switch_role_and_loc_if_required()
        self._set_dst_file()

    @abstractmethod
    def _extract_metadata(self):
        pass

    def _switch_role_and_loc_if_required(self):
        if self.role not in ["ech", "ech-quic", "ech-zdns", "cert-ech", "cert-ech-quic"]:
            temp = self.role
            self.role = self.loc
            self.loc = temp

    def _set_dst_file(self):
        self.dst_file = self.dst_dir / self.role / self.loc / f"{self.date}.pq.zst"

    def get_dst_file(self):
        return self.dst_file

    def make_dst_file_dir(self):
        self.dst_file.parent.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def duckdb_parse(self):
        pass


class DataParser(ABC):
    def __init__(self, path: Path, glob: List[str], kind: Type[Dataset]):
        self.path = path
        self.glob = glob
        self.kind = kind

    def get_src_files(self):
        return list(reversed(sorted(f for pattern in self.glob for f in self.path.glob(pattern))))

    def get_dst_files(self):
        return list(sorted(map(lambda x: self.kind(x).get_dst_file(), self.get_src_files())))


psl = PublicSuffixList()


def get_sld(url):
    if url is None:
        return None
    try:
        sld = psl.privatesuffix(url, accept_unknown=True, keep_case=False)
        if sld is None and psl.is_public(url):
            return url
        return sld
    except Exception:
        return None


duckdb.create_function(
    "sld",
    get_sld,
    return_type="VARCHAR",
    null_handling="special",
)


@lru_cache(maxsize=128)
def process_with_echme(value):
    if value is None:
        return None
    try:
        result = subprocess.run(
            [f"{config.PROJ_ROOT}/tools/echme"], input=str(value), text=True, capture_output=True
        )
        return json.loads(result.stdout.strip())
    except Exception:
        return None


echme_return_type = """STRUCT(
    ech_public_key VARCHAR,
    ech_version INTEGER,
    ech_config_id INTEGER,
    ech_public_name VARCHAR,
    ech_kem VARCHAR,
    ech_cipher_suites STRUCT(kdf INTEGER, aead INTEGER)[],
    ech_max_name_length INTEGER,
    ech_raw_extensions VARCHAR
)[]"""

duckdb.create_function(
    "echme",
    process_with_echme,
    return_type=echme_return_type,
    null_handling="special",
)
