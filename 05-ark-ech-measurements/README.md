# Active ECH Measurements from CAIDA Ark

Measures Encrypted Client Hello (ECH) deployment from CAIDA Ark vantage points using `scamper` and stores the results as warts and Parquet files.

- `src/ark_ech_measurement/`: Python package with measurement source code and warts parser
- `systemd/`: user timer/service running the measurement hourly
- `Makefile`: measurement runs, S3 upload, and preprocessing recipes

## Per-Domain Measurement Pipeline

For each domain and each vantage point (`ECHMeasurementPipeline`):

1. DNS `HTTPS` query: records the published `ECHConfigList`, if any
2. DNS `A` query: to obtain the address to connect to
3. Plain HTTPS request: baseline, no ECH
4. HTTPS request with ECH GREASE: a rejecting server returns a retry config
5. HTTPS request with ECH: using the retry config from step 4

The `ECHConfigList` from step 1 is recorded for analysis but is not used to establish the ECH connection; step 5 uses the retry config the server offered in response to GREASE.

## Commands

Installed via `uv` (`pyproject.toml` defines the entrypoints):

| Command              | Purpose                                          |
| -------------------- | ------------------------------------------------ |
| `measure file`       | Run the pipeline for a CSV of `target` domains   |
| `measure domain`     | Run the pipeline for a single domain             |
| `measure nodes-meta` | Dump metadata about the selected Ark instances   |
| `analyze`            | Parse a `.warts.gz` capture into JSON or Parquet |

`measure` needs access to a scamper mux socket (`--mux /run/ark/mux`) and a comma-separated list of Ark instances (`--instances`).

## Usage

```sh
uv sync
make measure       # one measurement round, uploaded to S3
make preprocess    # convert all raw warts captures to Parquet
make setup         # install and enable the hourly systemd user timer
```

Raw captures are written to `${raw_data_dir}` in a timestamped directory, processed Parquet files to `${processed_dir}`; both are set in the `Makefile`.
