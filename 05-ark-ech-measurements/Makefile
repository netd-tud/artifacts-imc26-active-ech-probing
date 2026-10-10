measurement_name=ech-ark-2026.txt

# Raw measuremnt data
raw_data_dir=/mnt/data01/ech-discovery/data/raw/ark
processed_dir=/mnt/data01/ech-discovery/data/processed/ark
# Timestamp each measurement
timestamp=$(shell date --iso-8601=seconds --utc | sed 's/:/_/g')
work_dir=${raw_data_dir}/${timestamp}
window_size=200

# Internal data
internal_dir=internal
blocklist_dir=${internal_dir}/blocklists
blocklist_file=${blocklist_dir}/${measurement_name}

internal_dir:
	-mkdir -p ${internal_dir}

pull-blocklist: internal_dir
	echo "noop pulling blocklist"
	
data:
	-mkdir -p ${raw_data_dir}

instances=fil-us,san2-us,cld6-us,bfi-us,las-us,mdw3-us,cld5-us,cld4-us,okc2-us,rdu3-us,pvu-us,yyc-ca,mnz-us,lex-us,rdu2-us,bed-us,bre-de,bio-es,mhb-nz,hlz2-nz,blq-it,ams8-nl,bwi3-us,akl2-nz,abz2-uk,drs2-de,zrh3-ch,prg2-cz,mad2-es,ber2-de,svo-ru,adl-au,nap2-it,poa2-br,psa-it,sjj-ba,aep3-ar
measure: pull-blocklist data
	mkdir ${work_dir}
	{ echo "target"; tail -n +2 2026-04-19_1k-per-destination.csv | shuf; } > shuffled-domains.txt
	/home/jmuecke/ark_ech_measurement/.venv/bin/measure file --mux /run/ark/mux --window-size ${window_size} --instances ${instances} --outfile ${work_dir}/file.warts.gz shuffled-domains.txt --window-size 50 >${work_dir}/log.log 2>&1
	/home/jmuecke/ark_ech_measurement/.venv/bin/s3cmd sync -r ./${work_dir}/ s3://netds3o:research-data/jmuecke/ech-discovery/data/raw/ark/$(notdir $(work_dir))/
	rm -r ${work_dir}

ark-nodes.jsonl:
	/home/jmuecke/ark_ech_measurement/.venv/bin/measure nodes-meta --mux /run/ark/mux --instances ${instances} ark-nodes.jsonl

setup:
	mkdir -p ~/.config/systemd/user/
	cp -r systemd/. ~/.config/systemd/user/
	systemctl --user daemon-reload
	systemctl --user enable --now measure-ech.timer

.DELETE_ON_ERROR:
INPUTS  := $(wildcard $(raw_data_dir)/*/file.warts.gz)
STAMPS  := $(patsubst $(raw_data_dir)/%/file.warts.gz,$(processed_dir)/%/.analyzed,$(INPUTS))

preprocess: $(STAMPS)
	echo $(STAMPS)

$(processed_dir)/%/.analyzed: $(raw_data_dir)/%/file.warts.gz
	mkdir -p $(processed_dir)/$*
	analyze --parquet $(processed_dir)/$*/$*.pq.zst.tmp $(raw_data_dir)/$*/file.warts.gz
	mv $(processed_dir)/$*/$*.pq.zst.tmp $(processed_dir)/$*/$*.pq.zst
	touch $@
