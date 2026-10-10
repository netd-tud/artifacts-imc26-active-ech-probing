.PHONY: setup preparedata filter clean build run measure randomize

SHELL=/bin/bash

timestamp := $(shell date --iso-8601=seconds --utc | sed -e 's:\::_:g')
workdir=/data/ech/scanner
measurement_name=ech-2024.txt

blocked_domains_file=blocked_domains.txt
domain_list_file=ech_domains.txt
filtered_domains_file=filtered_domains.txt
shuffled_domains_file=shuf_domains.txt

zgrab_result_file=results.txt
zgrab_result_file_zstd=results.txt.zstd
zgrab_log_file=logs.log

rawdomain_list_file=${workdir}/ech_domains.txt
blocklistdir=${workdir}/blocklists
measurementdir=${workdir}/measurements/${timestamp}

# count is the number of domains to scan after filtering of
# the full domain list. Default will be all domains from
# filtered list unless specified other
# default set in target:filter
count=0

# setup creates required directories and files
# results are written to $workdir/measurements/$timestamp
setup:
	mkdir -p ${workdir}/build
	mkdir -p ${workdir}/blocklists
	mkdir -p ${measurementdir}/input
	mkdir -p ${measurementdir}/output

	touch ${measurementdir}/input/${blocked_domains_file}

latest_zdns_scan := /data/raw/$(shell ls -t /data/raw | head -n2 | tail -n1)/results.json.zst
preparedata:
	@if [ -f ${latest_zdns_scan} ]; then \
		zstd -d ${latest_zdns_scan} --stdout | rg "\"ech\":" | jq -c '.name' | tr -d '"' > ${workdir}/ech_domains.txt; \
	else \
		echo "[ERR] zdns scan for ${latest_zdns_scan} is empty!"; \
		echo "[INF] starting scan with latest ech enabled domains in: ${workdir}/ech_domains.txt"; \
	fi

# filter exprects a blocked_domains.txt containing
# all domains which should be excluded from the scan.
# Each listed domain must have the regular expression
# of: (^|\.)host\.top-level-domain
# This is to ensure that also all subdomains belonging to
# the domain are filtered out
# If the blocklist file is empty (wc -l == 0) the domain
# list is simply copied without filtering.
filter:
	@if [ -s ${measurementdir}/input/${blocked_domains_file} ]; then \
		rg -v -f ${measurementdir}/input/${blocked_domains_file} ${rawdomain_list_file} > ${measurementdir}/input/${filtered_domains_file}; \
	else \
		cp ${rawdomain_list_file} ${measurementdir}/input/${filtered_domains_file}; \
	fi

randomize:
	@if [ ${count} -eq 0 ]; then \
		echo "Using all available domains (after filitering) as scan input"; \
		cat ${measurementdir}/input/${filtered_domains_file} | sort | uniq | shuf > ${measurementdir}/input/${shuffled_domains_file}; \
		rm ${measurementdir}/input/${filtered_domains_file}; \
	else \
		echo "Using reduced (only ${count}) domains (after filitering) as scan input"; \
		cat ${measurementdir}/input/${filtered_domains_file} | sort | uniq | shuf > ${measurementdir}/input/tmp_shuf.txt; \
		head -n ${count} ${measurementdir}/input/tmp_shuf.txt > ${measurementdir}/input/${shuffled_domains_file}; \
	fi

	rm ${measurementdir}/input/blocked_domains.txt; \
	rm ${measurementdir}/input/filtered_domains.txt; \

clean:
	rm -r ${workdir}/build

# compile zgrab2 source code - executable is placed in $workdir/build
# no longer usable because forked go version is used which is not on server
# will use already build binary instead of building
build: clean
	cd ./zgrab2/cmd/zgrab2 && go build -o ../../../build/zgrab2 && cd -

# --validate-timing \
# --use-cf-trace \
#  --quic-timeout=10 \
# run actual measurement...
run:
	./build/zgrab2-linux ech \
		--measure-latency\
		--protos h1,h2,h3 \
		--conn-primer dns \
		--input-file=${measurementdir}/input/${shuffled_domains_file} \
		--log-file=${measurementdir}/output/${zgrab_log_file} \
		--senders=50 \
		--gomaxprocs=2 | zstd > ${measurementdir}/output/${zgrab_result_file_zstd}


measure: setup preparedata filter randomize run
