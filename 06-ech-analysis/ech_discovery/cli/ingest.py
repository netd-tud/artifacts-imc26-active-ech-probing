from pathlib import Path

import click

import ech_discovery.config as config
from ech_discovery.data.ingest.dataset import DataParser
from ech_discovery.data.ingest.ech import ECHData, ECHInputData
from ech_discovery.data.ingest.zdns import ZDNSData

# Raw source globs, relative to config.RAW_DATA_DIR
ZDNS_GLOB_LOCAL = "tud/ech-zdns/*/results.json.zst"
ZDNS_GLOB_CLOUD = "gcloud/ech-zdns/*/*/results.json.zst"
ECH_GLOB_LOCAL = "tud/ech/*/output/results.txt.zst"
CERT_ECH_GLOB_LOCAL = "tud/cert-ech/*/output/results.txt.zst"
ECH_GLOB_CLOUD = "gcloud/ech/*/*/output/results.txt.zst"
ECH_INPUT_GLOB_LOCAL = "tud/ech/*/input/shuf_domains.txt.zst"
ECH_INPUT_GLOB_CLOUD = "gcloud/ech/*/*/input/shuf_domains.txt.zst"
ECH_QUIC_GLOB_LOCAL = "tud/ech-quic/*/output/results.txt.zst"
CERT_ECH_QUIC_GLOB_LOCAL = "tud/cert-ech-quic/*/output/results.txt.zst"
ECH_QUIC_GLOB_CLOUD = "gcloud/ech-quic/*/*/output/results.txt.zst"
ECH_QUIC_INPUT_GLOB_LOCAL = "tud/ech-quic/*/input/shuf_domains.txt.zst"
ECH_QUIC_INPUT_GLOB_CLOUD = "gcloud/ech-quic/*/*/input/shuf_domains.txt.zst"

# dataset name -> (base dir, source globs, parser class)
DATASETS = {
    "ech": (config.RAW_DATA_DIR, [ECH_GLOB_LOCAL, ECH_GLOB_CLOUD], ECHData),
    "ech-quic": (
        config.RAW_DATA_DIR,
        [ECH_QUIC_GLOB_LOCAL, ECH_QUIC_GLOB_CLOUD],
        ECHData,
    ),
    "cert-ech": (config.RAW_DATA_DIR, [CERT_ECH_GLOB_LOCAL], ECHData),
    "cert-ech-quic": (config.RAW_DATA_DIR, [CERT_ECH_QUIC_GLOB_LOCAL], ECHData),
    "ech-input": (
        config.RAW_DATA_DIR,
        [ECH_INPUT_GLOB_LOCAL, ECH_INPUT_GLOB_CLOUD],
        ECHInputData,
    ),
    "ech-quic-input": (
        config.RAW_DATA_DIR,
        [ECH_QUIC_INPUT_GLOB_LOCAL, ECH_QUIC_INPUT_GLOB_CLOUD],
        ECHInputData,
    ),
    "zdns": (config.RAW_DATA_DIR, [ZDNS_GLOB_LOCAL, ZDNS_GLOB_CLOUD], ZDNSData),
}

dataset_argument = click.argument("dataset", type=click.Choice(DATASETS))


@click.group()
def ingest():
    pass


def _parser(dataset: str) -> DataParser:
    base_dir, globs, kind = DATASETS[dataset]
    return DataParser(base_dir, globs, kind)


def click_echo_list(items):
    click.echo(" ".join(map(str, items)))


@ingest.command()
@dataset_argument
def src(dataset: str):
    """List raw source files of a dataset."""
    click_echo_list(_parser(dataset).get_src_files())


@ingest.command()
@dataset_argument
def dst(dataset: str):
    """List interim destination files of a dataset."""
    click_echo_list(_parser(dataset).get_dst_files())


@ingest.command()
@dataset_argument
@click.argument("src", type=click.Path(exists=True, path_type=Path))
@click.option("--force", is_flag=True, help="Force recreation of files")
def parse(dataset: str, src: Path, force: bool):
    """Parse one raw source file into its interim parquet file."""
    kind = DATASETS[dataset][2]
    kind(src, force=force).duckdb_parse()
