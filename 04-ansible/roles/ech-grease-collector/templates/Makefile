.PHONY: setup filter build run measure randomize

SHELL=/bin/bash

# Output directory
timestamp := $(shell date --iso-8601=seconds --utc | sed -e 's:\::_:g')
workdir=/mnt/data01/ech-greased

measurementdir:=${workdir}/raw/${timestamp}
measurementdir_in:=${measurementdir}/input
measurementdir_out:=${measurementdir}/output

# Input files
rawdomain_list_file=${workdir}/domains.txt.zst

#Output files
domain_list_file=full_domains.txt
filtered_domains_file=filtered_domains.txt
shuffled_domains_file=shuf_domains.txt
zgrab_result_file_zstd=results.txt.zst
zgrab_log_file=logs.log
LOG_PIPE=${measurementdir_out}/${zgrab_log_file}

# Blocklist
blocked_domains_file=blocked_domains.txt
measurement_name=ech-2024-12.txt
blocklist_dir=/mnt/data01/blocklists


internal_dir:
	-mkdir -p ${blocklist_dir}

pull-blocklist: internal_dir
	git -C ${blocklist_dir} pull || GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new" git clone git@github.com:netd-tud/active-measurements-blocklists.git ${blocklist_dir}

pull-names:
	s3cmd sync --no-preserve {{ s3source }} ${rawdomain_list_file}


# count is the number of domains to scan after filtering of
# the full domain list. Default will be all domains from
# filtered list unless specified other
# default set in target:filter
count=0

# setup creates required directories and files
# results are written to $workdir/measurements/$timestamp
setup: pull-blocklist pull-names
	mkdir -p ${workdir}/blocklists ${measurementdir_in} ${measurementdir_out}

	cp ${blocklist_dir}/${measurement_name} ${measurementdir_in}/${blocked_domains_file}

# filter expects a blocked_domains.txt containing
# all domains which should be excluded from the scan.
# Each listed domain must have the regular expression
# of: (^|\.)host\.top-level-domain
# This is ensure that also all subdomains beloning to
# the domain are filtered out
# If the blocklist file is empty (wc -l == 0) the domain
# list is simply copied without filtering.
filter:
	@if [ -s ${measurementdir_in}/${blocked_domains_file} ]; then \
		zstdcat ${rawdomain_list_file} | rg -v -f ${measurementdir_in}/${blocked_domains_file} > ${measurementdir_in}/${filtered_domains_file}; \
	else \
		zstdcat ${rawdomain_list_file} ${measurementdir_in}/${filtered_domains_file}; \
	fi

randomize:
	@if [ ${count} -eq 0 ]; then \
		echo "Using all available domains (after filtering) as scan input"; \
		cat ${measurementdir_in}/${filtered_domains_file} | sort -u | shuf > ${measurementdir_in}/${shuffled_domains_file}; \
	else \
		echo "Using reduced (only ${count}) domains (after filtering) as scan input"; \
		cat ${measurementdir_in}/${filtered_domains_file} | sort -u | shuf > ${measurementdir_in}/tmp_shuf.txt; \
		head -n ${count} ${measurementdir_in}/tmp_shuf.txt > ${measurementdir_in}/${shuffled_domains_file}; \
		rm ${measurementdir_in}/tmp_shuf.txt; \
	fi
	
	rm ${measurementdir_in}/blocked_domains.txt ${measurementdir_in}/filtered_domains.txt;


# e run actual measurement...
run:
	@mkfifo $(LOG_PIPE)
	zstd <$(LOG_PIPE) > $(LOG_PIPE).zst &
	./zgrab2/zgrab2 ech \
		--measure-latency\
		--protos {{ ech_greased_protos}} \
		--greased \
{% if ech_greased_verify is defined and ech_greased_verify %}
		--verify \
{% endif %}
		--input-file=${measurementdir}/input/${shuffled_domains_file} \
		--log-file=${measurementdir}/output/${zgrab_log_file} \
		--senders={{ ech_greased_senders }} | zstd > ${measurementdir}/output/${zgrab_result_file_zstd}
	rm $(LOG_PIPE)
	zstd --rm ${measurementdir_in}/${shuffled_domains_file}
{%if cloud is defined %}
	$(MAKE) push timestamp=$(timestamp)


push: REGION=$(shell curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/zone | cut -d'/' -f4 | sed 's/\(.*\)-.*/\1/')
push: ROLE=$(shell curl -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/role)
push: 
	curl -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/?recursive=true&alt=json" > ${measurementdir}/instance.json

	s3cmd -c /home/jmuecke/.s3cfg-netds3o put -r ${measurementdir} s3://netds3o:research-data/jmuecke/ech-discovery/data/raw/gcloud/${ROLE}/${REGION}/
	# Remove after upload to keep free storage
	rm -r ${measurementdir}

{% endif %}

measure-dry-run: setup filter

measure: setup filter randomize run
