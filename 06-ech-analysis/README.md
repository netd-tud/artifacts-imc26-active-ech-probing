# Data Analysis

<a target="_blank" href="https://cookiecutter-data-science.drivendata.org/">
    <img alt="CCDS Project template" src="https://img.shields.io/badge/CCDS-Project%20template-328F97?logo=cookiecutter" />
</a>

This folder contains the source code that creates the tables, graphs, and values in our paper.

> [!WARNING]
> Due to storage restrictions most data (~2.2 TB) must be downloaded from [OPARA](https://doi.org/10.25532/OPARA-1595).
> We do not include proprietary data (e.g., IPinfo).
> You must provide your own datasets instead.

## Setup

```sh
make create_environment
uv sync
make download                  # Download data from OPARA
```

## Project Organization

```text
├── Makefile           <- Ingest, aggregation, follow-up measurement and notebook recipes
├── data               <- Measurement dataset
│   ├── external       <- Third party data: put your own IPinfo mmdbs here
│   ├── raw            <- Raw measurement data: we include the structure only and provide the preprocessed data in interim.
│   │   ├── tud        <- Local vantage point: long-term measurements (ech, ech-quic, ech-zdns)
│   │   │                 and follow-up data collection (A, NS, zgrab2, echtool)
│   │   ├── gcloud     <- Cloud vantage points: ech, ech-quic, ech-zdns (one dir per location)
│   │   └── ark        <- CAIDA Ark captures and ark-nodes.jsonl (see 05-ark-ech-measurements)
│   ├── interim        <- Parsed measurements, <role>/<location>/<timestamp>.pq.zst, and the
│   │                     per-measurement aggregates written next to them (stats_, latency-stats_, …)
│   └── processed      <- Aggregated data for faster creation of plots
│
├── notebooks          <- Analysis notebooks, executed by `make run-notebooks`.
│
├── reports            <- values.tex, numbers used within the paper
│   └── figures        <- Generated figures
│
├── tools              <- Tools for short follow-up analysis and parsing: zdns, zgrab2, echtool (submodule builds), echme, export_targets.py
│
└── ech_discovery      <- Python module with shared source code and constants
    ├── config.py             <- Paths and constants (public names, data directories)
    ├── cli/                  <- `data ingest|aggregate|values`, the `data` entrypoint
    ├── data
    │   ├── ingest/           <- raw -> interim parsers (DuckDB)
    │   ├── aggregates/       <- interim -> aggregated datasets
    │   ├── enrichment/       <- ECH/zdns/IP helpers used by the aggregates
    │   ├── values/           <- creates reports/values.tex
    │   ├── loaders.py        <- Globs and scan helpers for interim and aggregated files
    │   ├── ranges.py         <- Measurement periods (main, followup, error-stats, all)
    │   └── columns.py, mapper.py <- Column names and label/CDN mappings
    └── plot/, notebook.py    <- Plotting helpers used by the notebooks
```

## Reproducibility

### Reproducing the Data Analysis

> [!WARNING]
> You must first download the processed data from OPARA (`make download`, [OPARA](https://doi.org/10.25532/OPARA-1595)).
> All other steps will fail otherwise.
> We cannot include data from third party data providers (e.g., IPinfo).
> You must provide your own IPinfo data and adapt file names in `ech_discovery/data/enrichment/ip.py`.

#### Data Preprocessing

```text
1  uv run data aggregate multi-ech-domains      # must be first, all other aggregates filter on it
2  uv run data aggregate follow-domains         # track ECH-capable domains throughout the measurements
3  make data_aggregations                       # all remaining aggregates, incl. `aggregate paper`
```

#### Values and Plots of the Paper

```text
4  make paper-values                            # reports/values.tex
5  make run-notebooks                           # reports/figures/ + the echtool_* aggregates
```

### Reproducing Follow-Up Measurements

For follow-up analyses, we collect A and NS records, perform TLS handshakes and infer grace periods on snapshots of our measurement data.
These were created using the following commands:

```sh
make submodules && make tools                   # requires Go 1.26.5
make measure-targets DATE=YYYY-MM-DD            # needs step 1
make measure-ns-records  DATE=YYYY-MM-DD        # needs step 1
make measure-cdn-share   DATE=YYYY-MM-DD
make measure-tls-version DATE=YYYY-MM-DD        # needs quic_only_domains_all from step 3
make measure-grace-period-{tcp,quic} DATE=YYYY-MM-DD
make measure-config-variations-{tcp,quic}[-insecure] DATE=YYYY-MM-DD
```

## Data Processing Details

### 1. Ingest (`uv run data ingest`)

> [!NOTE]
> We include the data produced by this step.
> We do not include its input data due to space constraints.

`uv run data ingest src <dataset>` lists the raw inputs and `uv run data ingest dst <dataset>` the interim outputs.
`uv run data ingest parse <dataset> <file>` parses one file.
The `make` targets use GNU parallel.

| Make target           | Dataset          | Input (`data/raw`)                                | Output (`data/interim`)                                        |
| --------------------- | ---------------- | ------------------------------------------------- | -------------------------------------------------------------- |
| `data-ech`            | `ech`            | `{tud,gcloud}/ech/**/output/results.txt.zst`      | `ech/<loc>/<ts>.pq.zst` + `errors_<ts>.pq.zst`                 |
| `data-ech-quic`       | `ech-quic`       | `{tud,gcloud}/ech-quic/**/output/results.txt.zst` | `ech-quic/<loc>/<ts>.pq.zst` + `errors_<ts>.pq.zst`            |
| `data-ech-input`      | `ech-input`      | `{tud,gcloud}/ech/**/input/shuf_domains.txt.zst`  | `ech/<loc>/input_<ts>.pq.zst` + `input_stats_<ts>.pq.zst`      |
| `data-ech-quic-input` | `ech-quic-input` | `…/ech-quic/**/input/shuf_domains.txt.zst`        | `ech-quic/<loc>/input_<ts>.pq.zst` + `input_stats_<ts>.pq.zst` |
| `data-zdns`           | `zdns`           | `{tud,gcloud}/ech-zdns/**/results.json.zst`       | `ech-zdns/<loc>/<ts>.pq.zst`                                   |

Parsing flattens the nested `JSONL` input, adds `measurement`/`role`/`location` from the path and the second level domain from the public suffix list.
The zdns parser additionally decodes the `ech` SVCB parameter with `tools/echme` into `ech_processed`.
`errors_*` holds domain counts per error reason, `input_stats_*` the input-list size per run.

Notes:

- For efficiency existing outputs are skipped.
  Pass `FORCE=1` (`make data-ech FORCE=1`) or `--force` to redo them.
- `FILTER='<regex>'` restricts the input files of `data-ech`/`data-ech-quic`.
- Parallelism is memory-bound: `PREPROCESS_PARALLELITY{,_LOW_MEM,_HIGH_MEM}`.

### 2. Aggregates (`uv run data aggregate`)

#### Per-Measurement Aggregates

| Command                    | Output (per interim file)                      | Content and method                                                                                                                                                                                                                |
| -------------------------- | ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `public-names`             | `stats_<ts>.pq.zst`                            | Domains per (public name, measurement, role, location, ECH-in-DNS), `kind` = `accepted` or `failed_retry` (ECH failed although retry configs were offered). ECH-in-DNS comes from the closest zdns snapshot of the same location. |
| `public-names-total`       | `total_stats_<ts>.pq.zst` (tud TCP files only) | Domains per public name over one tud run plus the closest preceding QUIC run. The extra `not-cloudflare-meta` row is the deduplicated domain count over all other public names.                                                   |
| `latency`                  | `latency-stats_<ts>`, `meas-duration_<ts>`     | Handshake duration median/mean/q90/q95/q99 with and without ECH and the median difference, in ms, per (role, measurement, location).                                                                                              |
| `sld-counts`               | `sld-count_<ts>.pq.zst`                        | Unique SLDs that accepted ECH, per (role, measurement, location).                                                                                                                                                                 |
| `retry-configs-first-seen` | `retry-configs-first-seen_<ts>.pq.zst`         | First timestamp per (measurement, role, location, public name, `retry_configs`) value.                                                                                                                                            |

#### Per-Measurement-Range Aggregates

| Range         | Period                  |
| ------------- | ----------------------- |
| `main`        | 2025-07-01 – 2025-11-06 |
| `followup`    | 2026-05-28 – 2026-08-15 |
| `error-stats` | 2025-07-14 – 2025-11-06 |
| `all`         | unbound                 |

Written to `data/processed/<name>[_<range>].pq.zst`.

| Command                                  | Output                                                                | Content and method                                                                                                                                                                                                                                   |
| ---------------------------------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `multi-ech-domains`                      | `multi-ech-domains_all`, `multi-ech-domains_cloudflare_and_meta`      | First sighting of every (domain, public name) pair across all `ech`, `ech-quic` and `ech-zdns` files. The second file lists domains seen with both a Cloudflare and a Meta public name, which is implausible; every other aggregate anti-joins them. |
| `follow-domains`                         | `follow-ech-domains`                                                  | Domains that accepted ECH in the tud TCP run of 2025-07-14 (`ranges.follow_domain_date`).                                                                                                                                                            |
| `error-stats`                            | `error_statistics_followed_domains`                                   | Properties of the `follow-domains` within subsequent measurements.                                                                                                                                                                                   |
| `follow-error-asn`                       | `follow_error_asn`                                                    | ASNs of the `follow-domains` with errors from the IPinfo MMDB.                                                                                                                                                                                       |
| `cdn-domains`                            | `cdn_domains`                                                         | CDNs per domain: A-record scan (`data/raw/tud/A/2026-08*`).                                                                                                                                                                                          |
| `ech-config-id-per-time-and-public-name` | `ech_config_id_per_time_and_public_name_<range>`                      | Domains per (minute, config id, public name, role, location) over TCP, QUIC and zdns (zdns: first sighting per name, combinations with ≤2 observations dropped).                                                                                     |
| `timing`                                 | `timing_statistics_<range>` (`timing_statistics_fine_<freq>_<range>`) | Histogram (200 µs buckets, reported in ms) of the with-ECH minus without-ECH handshake duration per (measurement, public name, role, location), over ECH-accepting connections. `--freq 5m` buckets by time window instead of by run.                |
| `timing-dispersion`                      | `timing_dispersion_<range>` (`…_fine_<freq>_…`)                       | Std, median absolute deviation and IQR (q25/q75) of the same difference per (measurement, role, location), all public names pooled.                                                                                                                  |
| `paper`                                  | see below                                                             | Runs every aggregate the paper's values need.                                                                                                                                                                                                        |

`uv run data aggregate paper` produces:

| Output                       | Content and method                                                                                                                                                               |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dns_status_<range>`         | Unique names per (measurement, location, zdns status) for two domain sets: the `follow-domains` and the Cloudflare+Meta domains. Needs `follow-domains` and `multi-ech-domains`. |
| `quic_only_domains_<range>`  | SLDs that accepted ECH over QUIC but in no TCP run of the closest preceding measurement day, with their TLD.                                                                     |
| `meta_fbsbx_domains_<range>` | SLDs with the Meta public name per (day, location), split by whether they end in `.apps.fbsbx.com`.                                                                              |
| `follow_error_tlds`          | TLDs of `follow-domains` with errors.                                                                                                                                            |
| `follow_error_asn`           | As `follow-error-asn` above.                                                                                                                                                     |
| `retry_provided`             | Unique SLDs per (date, location) that failed ECH but offered retry configs; each TCP run counted together with the closest preceding QUIC run of the same location.              |
| `accepted_sld`               | Unique SLDs that accepted ECH per (date, location), same TCP+QUIC pairing.                                                                                                       |
| `cdn_domains`                | As `cdn-domains` above.                                                                                                                                                          |
| `cf_meta_ns_location`        | Cloudflare+Meta domains split by whether any of their name servers sits in an AS registered in Asia; from the newest `data/raw/tud/NS` snapshot.                                 |
| `ark_timing`                 | Median ECH-minus-plain-TLS handshake RTT per public-name group (`cloudflare`, `meta`, `main`, `all`) plus the measurement span, from `data/processed/ark`.                       |

Aggregates resolving IPs (`cdn-domains`, `follow-error-asn`, `cf_meta_ns_location`) need the IPinfo MMDBs in `data/external/ipinfo/`.
These are not included with the artifacts.
You must provide your own IPinfo data.

### 3. Follow-Up Measurements

All targets need `DATE=YYYY-MM-DD` of a day on which tud ran both `ech` and `ech-quic`, so results stay comparable.
`make measure-targets` must run first: it samples up to 50 domains per public name into `data/raw/tud/echtool/targets/<DATE>/{targets.txt,domains.csv,criteria.json}`.
`make measure-targets-ark` writes a 1000-per-public-name list into the `ark/` subdirectory.

| Target                                 | Tool    | Output                                                                                   | Purpose                                                                             |
| -------------------------------------- | ------- | ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `measure-tls-version`                  | zgrab2  | `data/raw/tud/zgrab2/v771_<ts>.jsonl.zst`, `v772_…`                                      | TLS 1.2/1.3 probe of Cloudflare's QUIC-only domains (from `quic_only_domains`)      |
| `measure-ns-records`                   | zdns    | `data/raw/tud/NS/<ts>.jsonl.zst`                                                         | NS records of the Cloudflare+Meta domains                                           |
| `measure-cdn-share`                    | zdns    | `data/raw/tud/A/<ts>.jsonl.zst`                                                          | A records of the whole input list                                                   |
| `measure-grace-period-{tcp,quic}`      | echtool | `data/raw/tud/echtool/grace-period-<transport>/<ts>/`                                    | 168 h observation of ECH config rotation                                            |
| `measure-config-variations-*-insecure` | echtool | `data/raw/tud/echtool/configuration-variations-<transport>-cert-noverify/<ts>.jsonl.zst` | Server reaction to modified public names, config ids, outer SNI and max name length |

### 4. Notebooks

`make run-notebooks` executes notebooks under `notebooks/` in place and stops the Jupyter servers afterwards.
They read the aggregates and write into `reports/figures/`.

> [!NOTE]
> We exclude notebooks that require additional data (e.g., IPinfo datasets).

### 5. Paper Values

```sh
make paper-values
```

Writes `reports/values.tex` with `\setval` commands (read in the paper via `\getval`) for the ranges `main`, `followup` and `all`.
It reads the per-measurement aggregates (`stats_`, `total_stats_`, `latency-stats_`, `input_stats_`), the processed aggregates above, the newest zgrab2 TLS-version scan pair in `data/raw/tud/zgrab2/` and `data/raw/ark/ark-nodes.jsonl`.

### Other Notes

`tools/echme` is an earlier version of `echtool dech`: an ECHConfigList decoder with slightly different output structure.
