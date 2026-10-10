SHELL       := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

SERVER_NAME    ?= a.example.com
RESULTS        := results
CONFIGS        := configs

include ../containers.mk

.PHONY: profile profile-nginx profile-apache profile-report profile-check \
        build-ech-client build-nginx-ech build-apache-ech clean clean-images

PERF                   ?= perf
PERF_SUDO              ?= sudo
PERF_FREQ              ?= 1000
PERF_CALLGRAPH         ?= lbr
SERVER_CPUS            ?= 2,3
CLIENT_CPUS            ?= 4,5,6,7
PROFILE_PORT           ?= 54321
PROFILE_COUNT          ?= 50000
PROFILE_RECORD_COUNT   ?= $(PROFILE_COUNT)
PROFILE_PARALLEL       ?= 4
PROFILE_WARMUP         ?= 1000

PROFILE_CLIENT_HZ      ?= 1000
PROFILE_NGINX_VERSION  ?= 1.31.0
PROFILE_APACHE_VERSION ?= trunk
PROFILE_RESULTS        := $(RESULTS)/profile

ECH_CLIENT_BIN    ?= ech-client-bin

NGINX_ECH_REF    := $(NGINX_ECH_IMAGE):$(PROFILE_NGINX_VERSION)$(NGINX_TAG_SUFFIX)
NGINX_ECH_STAMP  := $(CONTAINERS)/nginx-ech/.built-$(PROFILE_NGINX_VERSION)
APACHE_ECH_REF   := $(APACHE_ECH_IMAGE):$(PROFILE_APACHE_VERSION)$(APACHE_TAG_SUFFIX)
APACHE_ECH_STAMP := $(CONTAINERS)/apache-ech/.built-$(PROFILE_APACHE_VERSION)

ECH_CONFIG_B64 = $(shell awk '/BEGIN ECHCONFIG/{f=1;next}/END ECHCONFIG/{f=0}f' $(CONFIGS)/nginx/ech/ech.pem | tr -d '\n')

profile: profile-nginx profile-apache profile-report

build-ech-client: $(ECH_CLIENT_BIN)
$(ECH_CLIENT_BIN): ech-client/main.go ech-client/go.mod
	@echo "=== building ech-client (go) ==="
	go build -C ech-client -o "$(CURDIR)/$(ECH_CLIENT_BIN)" .

build-nginx-ech: $(NGINX_ECH_STAMP)
build-apache-ech: $(APACHE_ECH_STAMP)

profile-check:
	@command -v $(PERF) >/dev/null 2>&1 || { echo "ERROR: '$(PERF)' not found. Please install."; exit 1; }
	@command -v taskset >/dev/null 2>&1 || { echo "ERROR: taskset not found. Please install."; exit 1; }
	@# Cache the sudo credential up front. Otherwise the password prompt lands
	@# between the background client launch and `perf record`, and the load has
	@# already run out by the time recording starts.
	@$(PERF_SUDO) -v
	@echo "profile-check: perf + taskset OK"

define capture_perf
	outdir="$(1)"; echarg="$(2)"; container="$(3)"
	echo "  client profile pass ($(PROFILE_COUNT) connections)"
	taskset -c $(CLIENT_CPUS) ./$(ECH_CLIENT_BIN) \
	      -host 127.0.0.1 -port $(PROFILE_PORT) -count $(PROFILE_COUNT) \
	      -parallel $(PROFILE_PARALLEL) -warmup $(PROFILE_WARMUP) \
	      -sni $(SERVER_NAME) $$echarg -json "$$outdir/client.json" \
	      -cpuprofile "$$outdir/client-cpu.pprof" -cpuprofhz $(PROFILE_CLIENT_HZ) \
	      > "$$outdir/client.txt" 2>&1 || true
	echo "  perf record pass: warmup ($(PROFILE_WARMUP) connections, not recorded)"
	taskset -c $(CLIENT_CPUS) ./$(ECH_CLIENT_BIN) \
	      -host 127.0.0.1 -port $(PROFILE_PORT) -count 0 \
	      -parallel $(PROFILE_PARALLEL) -warmup $(PROFILE_WARMUP) \
	      -sni $(SERVER_NAME) $$echarg -json /dev/null -quiet >/dev/null 2>&1 || true
	echo "  perf record pass: recording ($(PROFILE_RECORD_COUNT) connections)"
	( taskset -c $(CLIENT_CPUS) ./$(ECH_CLIENT_BIN) \
	      -host 127.0.0.1 -port $(PROFILE_PORT) -count $(PROFILE_RECORD_COUNT) \
	      -parallel $(PROFILE_PARALLEL) -warmup 0 \
	      -sni $(SERVER_NAME) $$echarg -json /dev/null -quiet >/dev/null 2>&1 ) &
	rpid=$$!
	pids=$$($(PODMAN) top "$$container" hpid 2>/dev/null | tail -n +2 | paste -sd,)
	$(PERF_SUDO) $(PERF) record -p "$$pids" -e cycles:u --call-graph $(PERF_CALLGRAPH) -F $(PERF_FREQ) \
	    -o "$$outdir/perf.data" \
	    -- bash -c 'while kill -0 '"$$rpid"' 2>/dev/null; do sleep 0.02; done' >/dev/null 2>&1 || true
	wait "$$rpid" 2>/dev/null || true
	symfs="$$outdir/symfs"; rm -rf "$$symfs"; mkdir -p "$$symfs"
	$(PERF_SUDO) $(PERF) buildid-list -i "$$outdir/perf.data" 2>/dev/null \
	    | awk '{print $$NF}' | grep '^/' | sort -u | while read -r p; do
	        case "$$p" in /proc/*|/dev/*|/sys/*|/memfd:*|/anon*|*//anon*) continue;; esac
	        mkdir -p "$$symfs$$(dirname "$$p")"
	        $(PODMAN) cp "$$container:$$p" "$$symfs$$p" 2>/dev/null || true
	    done
	$(PERF_SUDO) chown -R $$(id -u):$$(id -g) "$$outdir/perf.data" "$$symfs" 2>/dev/null || true
	$(PERF) report -i "$$outdir/perf.data" --symfs="$$symfs" --stdio --inline --percent-limit 0.5 \
	    2>/dev/null > "$$outdir/perf-report.txt" || true
endef

nginx_confdir  := /etc/nginx
nginx_files    := nginx.conf a.example.com.pem a.example.com.key ech.pem
apache_confdir := /usr/local/apache2/conf
apache_files   := httpd.conf a.example.com.pem a.example.com.key echkeys

# $(call profile_server,<server>,<test>,<cfg>,<image>,<client ech args>)
define profile_server
	test="$(2)"; cfg="$(3)"; image="$(4)"; echarg="$(5)"
	outdir="$(PROFILE_RESULTS)/$(1)/$$test"
	container="prof-$(1)-$$test"
	mkdir -p "$$outdir"
	$(PODMAN) rm -f "$$container" >/dev/null 2>&1 || true
	trap '$(PODMAN) rm -f "'"$$container"'" >/dev/null 2>&1 || true' EXIT
	echo "=== profiling $(1) [$$test]  $$image ==="
	mounts=()
	for f in $($(1)_files); do
	    mounts+=(-v "$(CURDIR)/$(CONFIGS)/$(1)/$$cfg/$$f:$($(1)_confdir)/$$f:ro,Z")
	done
	$(PODMAN) run -d --rm --name "$$container" --network host \
	    "$${mounts[@]}" "$$image" >/dev/null
	for _ in $$(seq 1 50); do
	    (exec 3<>/dev/tcp/127.0.0.1/$(PROFILE_PORT)) 2>/dev/null && { exec 3<&- 3>&-; break; }
	    sleep 0.2
	done
	for hp in $$($(PODMAN) top "$$container" hpid 2>/dev/null | tail -n +2); do
	    taskset -a -cp $(SERVER_CPUS) "$$hp" >/dev/null 2>&1 || true
	done
	$(call capture_perf,$$outdir,$$echarg,$$container)
	$(PODMAN) logs "$$container" > "$$outdir/server.log" 2>&1 || true
	$(PODMAN) rm -f "$$container" >/dev/null 2>&1 || true
endef

profile-nginx: profile-check build-ech-client $(NGINX_ECH_STAMP)
	@$(call profile_server,nginx,ech-off,base,$(NGINX_ECH_REF),)
	$(call profile_server,nginx,ech-on,ech,$(NGINX_ECH_REF),-ech $(ECH_CONFIG_B64))

profile-apache: profile-check build-ech-client $(APACHE_ECH_STAMP)
	@$(call profile_server,apache,ech-off,base,$(APACHE_ECH_REF),)
	$(call profile_server,apache,ech-on,ech,$(APACHE_ECH_REF),-ech $(ECH_CONFIG_B64))

profile-report:
	@python3 profile_report.py $(PROFILE_RESULTS)

clean-images:
	@$(PODMAN) rmi -f "$(NGINX_ECH_REF)" "$(APACHE_ECH_REF)" 2>/dev/null || true
	@rm -f "$(NGINX_ECH_STAMP)" "$(APACHE_ECH_STAMP)"

clean:
	rm -rf $(RESULTS) $(ECH_CLIENT_BIN)
