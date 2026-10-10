#################################################################################
# GLOBALS                                                                       #
#################################################################################

PROJECT_NAME = ech-discovery
PYTHON_VERSION = 3.13
PYTHON_INTERPRETER = python

#################################################################################
# COMMANDS                                                                      #
#################################################################################


## Install Python dependencies
.PHONY: requirements
requirements:
	uv pip install -r requirements.txt


## Delete all compiled Python files
.PHONY: clean
clean:
	find . -type f -name "*.py[co]" -delete
	find . -type d -name "__pycache__" -delete


## Lint using ruff (use `make format` to do formatting)
.PHONY: lint
lint:
	ruff format --check
	ruff check

## Format source code with ruff
.PHONY: format
format:
	ruff check --fix
	ruff format

## Set up Python interpreter environment
.PHONY: create_environment
create_environment:
	uv venv --python $(PYTHON_VERSION)
	@echo ">>> New uv virtual environment created. Activate with:"
	@echo ">>> Windows: .\\\\.venv\\\\Scripts\\\\activate"
	@echo ">>> Unix/macOS: source ./.venv/bin/activate"

#################################################################################
# EXTERNAL MEASUREMENT TOOLS (git submodules)                                   #
#################################################################################

ZDNS_DIR    = tools/zdns
ZGRAB2_DIR  = tools/zgrab2
ECHTOOL_DIR = ../02-echtool
ZDNS_BIN    = $(ZDNS_DIR)/zdns
ZGRAB2_BIN  = $(ZGRAB2_DIR)/zgrab2
ECHTOOL_BIN = tools/echtool

ZDNS_SRC    = $(shell find $(ZDNS_DIR)/src $(ZDNS_DIR)/main.go -type f -name '*.go' 2>/dev/null)
ZGRAB2_SRC  = $(shell find $(ZGRAB2_DIR) -type f -name '*.go' 2>/dev/null)
ECHTOOL_SRC = $(shell find $(ECHTOOL_DIR) -type f -name '*.go' 2>/dev/null)

## Build the vendored measurement tools (zdns, zgrab2, echtool)
.PHONY: tools
tools: $(ZDNS_BIN) $(ZGRAB2_BIN) $(ECHTOOL_BIN)

## Check out the pinned git submodules
.PHONY: submodules
submodules:
	git submodule update --init --recursive

$(ZDNS_DIR)/go.mod $(ZGRAB2_DIR)/go.mod:
	git submodule update --init --recursive

$(ZDNS_BIN): $(ZDNS_DIR)/go.mod $(ZDNS_SRC)
	cd $(ZDNS_DIR) && go generate ./... && go build -buildvcs=false -o zdns

$(ZGRAB2_BIN): $(ZGRAB2_DIR)/go.mod $(ZGRAB2_SRC)
	cd $(ZGRAB2_DIR) && go build -buildvcs=false -o zgrab2 ./cmd/zgrab2

$(ECHTOOL_DIR)/go.mod:
	git -C .. submodule update --init --recursive 02-echtool

$(ECHTOOL_BIN): $(ECHTOOL_DIR)/go.mod $(ECHTOOL_SRC)
	$(MAKE) -C $(ECHTOOL_DIR) build
	cp $(ECHTOOL_DIR)/bin/echtool $@

.PHONY: tools-clean
tools-clean:
	rm -f $(ZDNS_BIN) $(ZGRAB2_BIN) $(ECHTOOL_BIN)

#################################################################################
# PROJECT RULES                                                                 #
#################################################################################

# Parallelize with GNU parallel. Memory is the constraining factor.
PREPROCESS_PARALLELITY ?= 2
PREPROCESS_PARALLELITY_LOW_MEM ?= 6
PREPROCESS_PARALLELITY_HIGH_MEM ?= 1

# Pass FORCE=1 (e.g. `make data-ech FORCE=1`) to force recreation of already-parsed files.
FORCE ?=
FORCE_FLAG = $(if $(FORCE),--force,)

# regex to filter input file paths 
FILTER ?=

## Make dataset
.PHONY: data
data: requirements data-ech data-ech-input data-ech-quic-input data-ech-quic data-zdns

# Overall slowest operation. Must run only once.
data_aggregations_multi-ech-domains:
	uv run data aggregate multi-ech-domains

data_aggregations:
	uv run data aggregate public-names
	uv run data aggregate public-names-total
	uv run data aggregate latency
	uv run data aggregate sld-counts
	uv run data aggregate timing
	uv run data aggregate timing-dispersion
	uv run data aggregate timing-dispersion-time-of-day
	uv run data aggregate error-stats
	uv run data aggregate retry-configs-first-seen
	uv run data aggregate ech-config-id-per-time-and-public-name
	uv run data aggregate paper

## Generate values.tex for the paper (needs data_aggregations)
paper-values:
	uv run data values generate

IPINFO_NOTEBOOKS = notebooks/background/40-other-cdns.ipynb \
	notebooks/background/retryconfig-but-ech-fails/01-retry-and-ech-failed.ipynb

NOTEBOOKS = $(filter-out $(if $(wildcard data/external/ipinfo/*.mmdb),,$(IPINFO_NOTEBOOKS)), \
	$(shell find notebooks -name '*.ipynb' -not -path '*/.ipynb_checkpoints/*' \
	-not -path 'notebooks/ark/23-ark-locations.ipynb' | sort))

## Execute every notebook under notebooks/ in place, then stop the running Jupyter servers
.PHONY: run-notebooks
run-notebooks:
	uv run jupyter nbconvert --to notebook --execute --inplace $(NOTEBOOKS); status=$$?; \
	uv run jupyter server list --jsonlist | jq -r '.[].port' | xargs -r -n1 uv run jupyter server stop; \
	exit $$status

### RAW data processing for reference only. We publish already preprocessed data

data-ech: SRC=$(shell uv run data ingest src ech | tr ' ' '\n' | grep -E "$(FILTER)")
data-ech:
	parallel --bar -j $(PREPROCESS_PARALLELITY_HIGH_MEM) uv run data ingest parse ech $(FORCE_FLAG) {} ::: $(SRC)

data-ech-input: SRC=$(shell uv run data ingest src ech-input)
data-ech-input:
	parallel --bar -j $(PREPROCESS_PARALLELITY) uv run data ingest parse ech-input {} ::: $(SRC)

data-ech-quic-input: SRC=$(shell uv run data ingest src ech-quic-input)
data-ech-quic-input:
	parallel --bar -j $(PREPROCESS_PARALLELITY) uv run data ingest parse ech-quic-input --force {} ::: $(SRC)

data-ech-quic: SRC=$(shell uv run data ingest src ech-quic | tr ' ' '\n' | grep -E "$(FILTER)")
data-ech-quic:
	parallel --bar -j $(PREPROCESS_PARALLELITY_HIGH_MEM) uv run data ingest parse ech-quic $(FORCE_FLAG) {} ::: $(SRC)

data-zdns: SRC=$(shell uv run data ingest src zdns)
data-zdns:
	parallel --bar -j $(PREPROCESS_PARALLELITY_LOW_MEM) uv run data ingest parse zdns {} ::: $(SRC)

#################################################################################
# Measurements based on processed data (zgrab2, NS/A-record, echtool)           #
#################################################################################

# DATE is required for every target below (YYYY-MM-DD). Make sure it is a date on which both ech and ech-quic ran.
# measure targets must run before all below measurements
## Sample up to 50 domains/ECH public name
measure-targets:
	uv run python tools/export_targets.py sample --date $(DATE)

## Sample up to 1000 domains/ECH public name for the Ark measurement
measure-targets-ark:
	uv run python tools/export_targets.py sample --date $(DATE) --per-public-name 1000 --tag ark

######### zgrab2 #########

## TLS-version probe (zgrab2) of Cloudflare's QUIC-only domains
measure-tls-version: TIMESTAMP=$(shell date --iso-8601=seconds --utc | sed 's/:/_/g')
measure-tls-version: $(ZGRAB2_BIN)
	mkdir -p data/raw/tud/zgrab2
	uv run python tools/export_targets.py cf-quic-only --date $(DATE) --criteria-file data/raw/tud/zgrab2/v771_$(TIMESTAMP)-criteria.json | $(ZGRAB2_BIN) tls --min-version=771 | jq "{version: .data.tls.result.handshake_log.server_hello.supported_versions.selected_version.name, domain: .domain, error: (.data.tls.error//.error)}" -c | zstd > data/raw/tud/zgrab2/v771_$(TIMESTAMP).jsonl.zst
	uv run python tools/export_targets.py cf-quic-only --date $(DATE) --criteria-file data/raw/tud/zgrab2/v772_$(TIMESTAMP)-criteria.json | $(ZGRAB2_BIN) tls --min-version=772 | jq "{version: .data.tls.result.handshake_log.server_hello.supported_versions.selected_version.name, domain: .domain, error: (.data.tls.error//.error)}" -c | zstd > data/raw/tud/zgrab2/v772_$(TIMESTAMP).jsonl.zst

######### zdns #########

## NS-record lookup for Cloudflare+Meta multi-CDN domains
measure-ns-records: TIMESTAMP=$(shell date --iso-8601=seconds --utc | sed 's/:/_/g')
measure-ns-records: $(ZDNS_BIN)
	mkdir -p data/raw/tud/NS
	uv run python tools/export_targets.py cf-meta --date $(DATE) --criteria-file data/raw/tud/NS/$(TIMESTAMP)-criteria.json | $(ZDNS_BIN) NSLOOKUP | zstd > data/raw/tud/NS/$(TIMESTAMP).jsonl.zst

## A-record lookup for CDN-share classification
measure-cdn-share: TIMESTAMP=$(shell date --iso-8601=seconds --utc | sed 's/:/_/g')
measure-cdn-share: $(ZDNS_BIN)
	mkdir -p data/raw/tud/A
	uv run python tools/export_targets.py all-input --date $(DATE) --criteria-file data/raw/tud/A/$(TIMESTAMP)-criteria.json | $(ZDNS_BIN) ALOOKUP --ipv4-lookup --name-servers 8.8.8.8,1.1.1.1,8.8.4.4,1.0.0.1 --result-verbosity short | zstd > data/raw/tud/A/$(TIMESTAMP).jsonl.zst

######### echtool #########

## grace-period with TCP
measure-grace-period-tcp: TIMESTAMP=$(shell date --iso-8601=seconds --utc | sed 's/:/_/g')
measure-grace-period-tcp:
	mkdir -p data/raw/tud/echtool/grace-period-tcp/$(TIMESTAMP)
	xargs -a data/raw/tud/echtool/targets/$(DATE)/targets.txt tools/echtool test grace-period --transport tcp --max-runtime 168h --state-dir data/raw/tud/echtool/grace-period-tcp/$(TIMESTAMP)

## measure-grace-period-quic: TIMESTAMP=$(shell date --iso-8601=seconds --utc | sed 's/:/_/g')
measure-grace-period-quic:
	mkdir -p data/raw/tud/echtool/grace-period-quic/$(TIMESTAMP)
	xargs -a data/raw/tud/echtool/targets/$(DATE)/targets.txt tools/echtool test grace-period --transport quic --max-runtime 168h --state-dir data/raw/tud/echtool/grace-period-quic/$(TIMESTAMP)

# --ech-config-public-name / --outer-sni values below: 9256fd09b8b.com / 85c889ee334.de are the
# first 11 hex chars of `echo "ech-test"` / `echo "ech-test2"` piped through sha256sum -- the
#   $ echo "ech-test"  | sha256sum | cut -c1-11   ->  9256fd09b8b
#   $ echo "ech-test2" | sha256sum | cut -c1-11   ->  85c889ee334
ECHTOOL_VARIATION_FLAGS = --ech-config-public-name 9256fd09b8b.com --ech-config-public-name 85c889ee334.de --ech-config-public-name ech-test.com --ech-config-config-id 37 --ech-config-config-id 38 --ech-config-config-id 123 --outer-sni 9256fd09b8b.com --outer-sni 85c889ee334.de --outer-sni ech-test.com --outer-ech-config-id 37 --outer-ech-config-id 38 --outer-ech-config-id 123 --outer-max-name-length 0 --outer-max-name-length 123 --outer-max-name-length 255

## configuration-variations
measure-config-variations-tcp: TIMESTAMP=$(shell date --iso-8601=seconds --utc | sed 's/:/_/g')
measure-config-variations-tcp:
	mkdir -p data/raw/tud/echtool/configuration-variations-tcp-cert-verify
	xargs -a data/raw/tud/echtool/targets/$(DATE)/targets.txt tools/echtool test configuration-variations --transport tcp --format json $(ECHTOOL_VARIATION_FLAGS) | jq -c '.[]' | zstd > data/raw/tud/echtool/configuration-variations-tcp-cert-verify/$(TIMESTAMP).jsonl.zst

## echtool configuration-variations, TCP, all sampled domains in one run (certificate validation skipped)
measure-config-variations-tcp-insecure: TIMESTAMP=$(shell date --iso-8601=seconds --utc | sed 's/:/_/g')
measure-config-variations-tcp-insecure:
	mkdir -p data/raw/tud/echtool/configuration-variations-tcp-cert-noverify
	xargs -a data/raw/tud/echtool/targets/$(DATE)/targets.txt tools/echtool test configuration-variations --transport tcp --format json --insecure $(ECHTOOL_VARIATION_FLAGS) | jq -c '.[]' | zstd > data/raw/tud/echtool/configuration-variations-tcp-cert-noverify/$(TIMESTAMP).jsonl.zst

## echtool configuration-variations, QUIC, all sampled domains in one run (cert validation performed)
measure-config-variations-quic: TIMESTAMP=$(shell date --iso-8601=seconds --utc | sed 's/:/_/g')
measure-config-variations-quic:
	mkdir -p data/raw/tud/echtool/configuration-variations-quic-cert-verify
	xargs -a data/raw/tud/echtool/targets/$(DATE)/targets.txt tools/echtool test configuration-variations --transport quic --format json $(ECHTOOL_VARIATION_FLAGS) | jq -c '.[]' | zstd > data/raw/tud/echtool/configuration-variations-quic-cert-verify/$(TIMESTAMP).jsonl.zst

## echtool configuration-variations, QUIC, all sampled domains in one run (certificate validation skipped)
measure-config-variations-quic-insecure: TIMESTAMP=$(shell date --iso-8601=seconds --utc | sed 's/:/_/g')
measure-config-variations-quic-insecure:
	mkdir -p data/raw/tud/echtool/configuration-variations-quic-cert-noverify
	xargs -a data/raw/tud/echtool/targets/$(DATE)/targets.txt tools/echtool test configuration-variations --transport quic --format json --insecure $(ECHTOOL_VARIATION_FLAGS) | jq -c '.[]' | zstd > data/raw/tud/echtool/configuration-variations-quic-cert-noverify/$(TIMESTAMP).jsonl.zst

measure-all: measure-targets measure-tls-version measure-ns-records measure-cdn-share

DIST ?= dist
DATA_DIR ?= data

OPARA = https://opara.zih.tu-dresden.de/server/api/core/bitstreams
OPARA_IDS = \
        81638aa9-e671-47fb-9af9-5a8c8c97d6ca \
        225eadcb-467d-45e2-bde6-10e98957d563 \
        dec8fba7-4251-468c-ae61-f0ce5ca03227 \
        4de48685-8a14-4845-b805-e771d43a1d86 \
        28ce87c5-6bc4-4996-beea-8e9449839edd \
        f0cc3364-9838-4da2-add9-4da903dc5889 \
        55fdbbb8-d461-465a-92c2-b1448418042d \
        d5ecec97-f765-42e9-a871-6e5079d58ca8 \
        9bb26fb4-195c-43a1-a877-311571f27b3f \
        abf3c3d3-3f09-46dc-8bce-158447041ad6 \
        d7bf8e27-bfe9-4679-b7fd-0f5600eb4e36

## Download the archives from OPARA into $(DIST)/ and extract them
# Only works if the API does not change. Otherwise download manually from the linked DOI.
.PHONY: download
download:
        @mkdir -p $(DIST)
        @i=0; n=$(words $(OPARA_IDS)); \
        for id in $(OPARA_IDS); do \
                i=$$((i + 1)); \
                echo ">>> [$$i/$$n] $$id"; \
                (cd $(DIST) && curl --fail --location -OJ "$(OPARA)/$$id/content") || exit 1; \
        done
        $(MAKE) untar

.PHONY: untar
untar:
	@ls $(DIST)/*.tar >/dev/null 2>&1 || ls $(DIST)/*.tar.gz >/dev/null 2>&1 || \
		{ echo "no archives in $(DIST)/" >&2; exit 1; }
	@mkdir -p $(DATA_DIR)
	@for f in $(DIST)/*.tar $(DIST)/*.tar.gz; do \
		[ -e "$$f" ] || continue; \
		echo ">>> $$f"; \
		tar -xf "$$f" -C $(DATA_DIR); \
	done

#################################################################################
# Self Documenting Commands                                                     #
#################################################################################

.DEFAULT_GOAL := help

define PRINT_HELP_PYSCRIPT
import re, sys; \
lines = '\n'.join([line for line in sys.stdin]); \
matches = re.findall(r'\n## (.*)\n[\s\S]+?\n([a-zA-Z_-]+):', lines); \
print('Available rules:\n'); \
print('\n'.join(['{:25}{}'.format(*reversed(match)) for match in matches]))
endef
export PRINT_HELP_PYSCRIPT

help:
	@$(PYTHON_INTERPRETER) -c "${PRINT_HELP_PYSCRIPT}" < $(MAKEFILE_LIST)
