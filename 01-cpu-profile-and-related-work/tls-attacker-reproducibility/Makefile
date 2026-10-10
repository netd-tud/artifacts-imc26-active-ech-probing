SHELL       := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:

JAR         ?= ./TLS-Client.jar
PORT        ?= 54321
HOST        ?= localhost
SERVER_NAME ?= a.example.com

WORKFLOWS := TLS-grease \
             niere-unknown-extension-with-value \
             parsable-ech-extension \
             unparsable-ech-as-raw-extension

RESULTS := results
CONFIGS := configs

TLS_ATTACKER_REPO ?= https://github.com/tls-attacker/TLS-Attacker.git
TLS_ATTACKER_REF  ?= v7.5.1
TLS_ATTACKER_SRC  := .build/TLS-Attacker

include ../containers.mk

# --- nginx (stock) configuration ----------------------------------------------
NGINX_IMAGE        ?= docker.io/library/nginx
NGINX_VERSIONS     ?= 1.21.0 1.22.0 1.24.0 1.26.0 1.27.0 1.28.0 1.29.4 1.30.0 1.31.0

NGINX_ECH_VERSIONS    ?= 1.29.4 1.30.0 1.31.0

NGINX_BORINGSSL_VERSIONS ?= 1.29.4 1.30.0 1.31.0

APACHE_IMAGE        ?= docker.io/library/httpd
APACHE_VERSIONS     ?= 2.4.67

APACHE_ECH_VERSIONS ?= trunk

.PHONY: all nginx apache cloudflare external evaluate clean pull \
        build-nginx-ech build-nginx-boringssl build-apache-ech clean-images \
        build-jars

all: nginx apache evaluate

NGINX_BASE_DONES         := $(addsuffix /base/.done,         $(addprefix $(RESULTS)/nginx/,$(NGINX_VERSIONS)))
NGINX_ECH_DISABLED_DONES := $(addsuffix /ech-disabled/.done, $(addprefix $(RESULTS)/nginx/,$(NGINX_ECH_VERSIONS)))
NGINX_ECH_DONES          := $(addsuffix /ech/.done,          $(addprefix $(RESULTS)/nginx/,$(NGINX_ECH_VERSIONS)))
NGINX_BORINGSSL_DISABLED_DONES := $(addsuffix /boringssl-disabled/.done, $(addprefix $(RESULTS)/nginx/,$(NGINX_BORINGSSL_VERSIONS)))
NGINX_BORINGSSL_DONES          := $(addsuffix /boringssl/.done,          $(addprefix $(RESULTS)/nginx/,$(NGINX_BORINGSSL_VERSIONS)))
NGINX_ECH_BUILT          := $(addprefix ../containers/nginx-ech/.built-,       $(NGINX_ECH_VERSIONS))
NGINX_BORINGSSL_BUILT    := $(addprefix ../containers/nginx-boringssl/.built-, $(NGINX_BORINGSSL_VERSIONS))

nginx: $(NGINX_BASE_DONES) $(NGINX_ECH_DISABLED_DONES) $(NGINX_ECH_DONES) \
       $(NGINX_BORINGSSL_DISABLED_DONES) $(NGINX_BORINGSSL_DONES)

# Shared recipe body.
#   $(1) version (e.g. 1.29.4)
#   $(2) variant (result-dir name: base | ech-disabled | ech)
#   $(3) image repo (NGINX_IMAGE or NGINX_ECH_IMAGE)
#   $(4) config-dir name under configs/nginx/ (base | ech)
# Invoked from the pattern rules below.
define run_nginx_tests
	version="$(1)$(NGINX_TAG_SUFFIX)"
	variant="$(2)"
	image="$(3):$(1)$(NGINX_TAG_SUFFIX)"
	outdir="$(RESULTS)/nginx/$(1)/$(2)"
	container="eval-nginx-$(1)-$(2)"
	mkdir -p "$$outdir"
	$(PODMAN) rm -f "$$container" >/dev/null 2>&1 || true
	trap '$(PODMAN) stop "'"$$container"'" >/dev/null 2>&1 || true' EXIT
	echo "=== $$image ($$variant) ==="
	$(PODMAN) run -d --rm --name "$$container" -p $(PORT):54321 \
	    -v "$(CURDIR)/$(CONFIGS)/nginx/$(4)/nginx.conf:/etc/nginx/nginx.conf:ro,Z" \
	    -v "$(CURDIR)/$(CONFIGS)/nginx/$(4)/a.example.com.pem:/etc/nginx/a.example.com.pem:ro,Z" \
	    -v "$(CURDIR)/$(CONFIGS)/nginx/$(4)/a.example.com.key:/etc/nginx/a.example.com.key:ro,Z" \
	    -v "$(CURDIR)/$(CONFIGS)/nginx/$(4)/ech.pem:/etc/nginx/ech.pem:ro,Z" \
	    "$$image" >/dev/null
	# Wait for the port to accept connections (<= ~10 s).
	for _ in $$(seq 1 50); do
	    (exec 3<>/dev/tcp/127.0.0.1/$(PORT)) 2>/dev/null && { exec 3<&- 3>&-; break; }
	    sleep 0.2
	done
	for wf in $(WORKFLOWS); do
	    echo "  -> $$wf"
	    java -jar $(JAR) \
	        -connect $(HOST):$(PORT) \
	        -workflow_input "$$wf.xml" \
	        -server_name $(SERVER_NAME) -version TLS13 \
	        -keylogfile "$$outdir/$$wf.keylog" \
	        -workflow_output "$$outdir/$$wf.out.xml" \
	        > "$$outdir/$$wf.log" 2>&1 || true
	done
	$(PODMAN) logs "$$container" > "$$outdir/server.log" 2>&1 || true
endef

$(RESULTS)/nginx/%/base/.done: $(CONFIGS)/nginx/base/nginx.conf $(addsuffix .xml,$(WORKFLOWS))
	@$(call run_nginx_tests,$*,base,$(NGINX_IMAGE),base)
	touch $@

$(RESULTS)/nginx/%/ech-disabled/.done: $(CONFIGS)/nginx/base/nginx.conf $(addsuffix .xml,$(WORKFLOWS)) ../containers/nginx-ech/.built-%
	@$(call run_nginx_tests,$*,ech-disabled,$(NGINX_ECH_IMAGE),base)
	touch $@

$(RESULTS)/nginx/%/ech/.done: $(CONFIGS)/nginx/ech/nginx.conf $(addsuffix .xml,$(WORKFLOWS)) ../containers/nginx-ech/.built-%
	@$(call run_nginx_tests,$*,ech,$(NGINX_ECH_IMAGE),ech)
	touch $@

$(RESULTS)/nginx/%/boringssl-disabled/.done: $(CONFIGS)/nginx/base/nginx.conf $(addsuffix .xml,$(WORKFLOWS)) ../containers/nginx-boringssl/.built-%
	@$(call run_nginx_tests,$*,boringssl-disabled,$(NGINX_BORINGSSL_IMAGE),base)
	touch $@

$(RESULTS)/nginx/%/boringssl/.done: $(CONFIGS)/nginx/ech/nginx.conf $(addsuffix .xml,$(WORKFLOWS)) ../containers/nginx-boringssl/.built-%
	@echo "  ! WARNING: ECH is NOT enabled in the nginx-boringssl variant."
	@echo "  !          ssl_ech_file is #ifdef'd on SSL_OP_ECH_GREASE (defo-OpenSSL)"
	@echo "  !          which BoringSSL doesn't define. nginx will log:"
	@echo "  !            [warn] \"ssl_ech_file\" is not supported on this platform, ignored"
	@echo "  !          See $(RESULTS)/nginx/$*/boringssl/server.log to confirm."
	@$(call run_nginx_tests,$*,boringssl,$(NGINX_BORINGSSL_IMAGE),ech)
	touch $@

build-nginx-ech: $(NGINX_ECH_BUILT)

build-nginx-boringssl: $(NGINX_BORINGSSL_BUILT)

# --- apache targets -----------------------------------------------------------
APACHE_BASE_DONES         := $(addsuffix /base/.done,         $(addprefix $(RESULTS)/apache/,$(APACHE_VERSIONS)))
APACHE_ECH_DISABLED_DONES := $(addsuffix /ech-disabled/.done, $(addprefix $(RESULTS)/apache/,$(APACHE_ECH_VERSIONS)))
APACHE_ECH_DONES          := $(addsuffix /ech/.done,          $(addprefix $(RESULTS)/apache/,$(APACHE_ECH_VERSIONS)))
APACHE_ECH_BUILT          := $(addprefix ../containers/apache-ech/.built-,$(APACHE_ECH_VERSIONS))

apache: $(APACHE_BASE_DONES) $(APACHE_ECH_DISABLED_DONES) $(APACHE_ECH_DONES)

# Shared apache recipe body (paths differ from nginx).
#   $(1) version (e.g. 2.4 or 2.5.1)
#   $(2) variant (base | ech-disabled | ech)
#   $(3) image repo (APACHE_IMAGE or APACHE_ECH_IMAGE)
#   $(4) config-dir name under configs/apache/ (base | ech)
define run_apache_tests
	version="$(1)$(APACHE_TAG_SUFFIX)"
	variant="$(2)"
	image="$(3):$(1)$(APACHE_TAG_SUFFIX)"
	outdir="$(RESULTS)/apache/$(1)/$(2)"
	container="eval-apache-$(1)-$(2)"
	mkdir -p "$$outdir"
	$(PODMAN) rm -f "$$container" >/dev/null 2>&1 || true
	trap '$(PODMAN) stop "'"$$container"'" >/dev/null 2>&1 || true' EXIT
	echo "=== $$image ($$variant) ==="
	$(PODMAN) run -d --rm --name "$$container" -p $(PORT):54321 \
	    -v "$(CURDIR)/$(CONFIGS)/apache/$(4)/httpd.conf:/usr/local/apache2/conf/httpd.conf:ro,Z" \
	    -v "$(CURDIR)/$(CONFIGS)/apache/$(4)/a.example.com.pem:/usr/local/apache2/conf/a.example.com.pem:ro,Z" \
	    -v "$(CURDIR)/$(CONFIGS)/apache/$(4)/a.example.com.key:/usr/local/apache2/conf/a.example.com.key:ro,Z" \
	    -v "$(CURDIR)/$(CONFIGS)/apache/$(4)/echkeys:/usr/local/apache2/conf/echkeys:ro,Z" \
	    "$$image" >/dev/null
	# Wait for the port to accept connections (≤ ~10 s).
	for _ in $$(seq 1 50); do
	    (exec 3<>/dev/tcp/127.0.0.1/$(PORT)) 2>/dev/null && { exec 3<&- 3>&-; break; }
	    sleep 0.2
	done
	for wf in $(WORKFLOWS); do
	    echo "  -> $$wf"
	    java -jar $(JAR) \
	        -connect $(HOST):$(PORT) \
	        -workflow_input "$$wf.xml" \
	        -server_name $(SERVER_NAME) -version TLS13 \
	        -keylogfile "$$outdir/$$wf.keylog" \
	        -workflow_output "$$outdir/$$wf.out.xml" \
	        > "$$outdir/$$wf.log" 2>&1 || true
	done
	$(PODMAN) logs "$$container" > "$$outdir/server.log" 2>&1 || true
endef

$(RESULTS)/apache/%/base/.done: $(CONFIGS)/apache/base/httpd.conf $(addsuffix .xml,$(WORKFLOWS))
	@$(call run_apache_tests,$*,base,$(APACHE_IMAGE),base)
	touch $@

$(RESULTS)/apache/%/ech-disabled/.done: $(CONFIGS)/apache/base/httpd.conf $(addsuffix .xml,$(WORKFLOWS)) ../containers/apache-ech/.built-%
	@$(call run_apache_tests,$*,ech-disabled,$(APACHE_ECH_IMAGE),base)
	touch $@

$(RESULTS)/apache/%/ech/.done: $(CONFIGS)/apache/ech/httpd.conf $(addsuffix .xml,$(WORKFLOWS)) ../containers/apache-ech/.built-%
	@$(call run_apache_tests,$*,ech,$(APACHE_ECH_IMAGE),ech)
	touch $@

build-apache-ech: $(APACHE_ECH_BUILT)

# --- external server tests ----------------------------------------------------
# These targets hit a real, externally-operated server
define run_external_tests
	name="$(1)"
	host="$(2)"
	port="$(3)"
	sni="$(4)"
	outdir="$(RESULTS)/$$name/$$port/live"
	mkdir -p "$$outdir"
	echo "=== external: $$host:$$port (SNI=$$sni) ==="
	for wf in $(WORKFLOWS); do
	    echo "  -> $$wf"
	    java -jar $(JAR) \
	        -connect "$$host:$$port" \
	        -workflow_input "$$wf.xml" \
	        -server_name "$$sni" -version TLS13 \
	        -keylogfile "$$outdir/$$wf.keylog" \
	        -workflow_output "$$outdir/$$wf.out.xml" \
	        > "$$outdir/$$wf.log" 2>&1 || true
	done
endef

#  test against live server
cloudflare: $(RESULTS)/cloudflare/443/live/.done

$(RESULTS)/cloudflare/443/live/.done: $(addsuffix .xml,$(WORKFLOWS))
	@$(call run_external_tests,cloudflare,cloudflare.com,443,cloudflare.com)
	touch $@

external: cloudflare

# Pre-fetch stock images so the first test run doesn't include image-download time.
pull:
	@for v in $(NGINX_VERSIONS); do
	    echo "Pulling $(NGINX_IMAGE):$$v$(NGINX_TAG_SUFFIX)"
	    $(PODMAN) pull "$(NGINX_IMAGE):$$v$(NGINX_TAG_SUFFIX)"
	done
	@for v in $(APACHE_VERSIONS); do
	    echo "Pulling $(APACHE_IMAGE):$$v$(APACHE_TAG_SUFFIX)"
	    $(PODMAN) pull "$(APACHE_IMAGE):$$v$(APACHE_TAG_SUFFIX)"
	done

# Remove the locally built ECH images and their build stamps.
clean-images:
	@for v in $(NGINX_ECH_VERSIONS); do
	    $(PODMAN) rmi -f "$(NGINX_ECH_IMAGE):$$v$(NGINX_TAG_SUFFIX)" 2>/dev/null || true
	    rm -f "../containers/nginx-ech/.built-$$v"
	done
	@for v in $(NGINX_BORINGSSL_VERSIONS); do
	    $(PODMAN) rmi -f "$(NGINX_BORINGSSL_IMAGE):$$v$(NGINX_TAG_SUFFIX)" 2>/dev/null || true
	    rm -f "../containers/nginx-boringssl/.built-$$v"
	done
	@for v in $(APACHE_ECH_VERSIONS); do
	    $(PODMAN) rmi -f "$(APACHE_ECH_IMAGE):$$v$(APACHE_TAG_SUFFIX)" 2>/dev/null || true
	    rm -f "../containers/apache-ech/.built-$$v"
	done

evaluate:
	@python3 evaluate.py $(RESULTS)

# Requires JDK, and Maven
build-jars:
	@command -v mvn >/dev/null 2>&1 || { \
	    echo "error: mvn (Maven) is not installed or not on PATH; required to build TLS-Attacker from source" >&2; \
	    exit 1; \
	}
	@echo "=== Building TLS-Attacker jars from $(TLS_ATTACKER_REPO) @ $(TLS_ATTACKER_REF) ==="
	rm -rf "$(TLS_ATTACKER_SRC)"
	mkdir -p "$(dir $(TLS_ATTACKER_SRC))"
	git clone --depth 1 --branch "$(TLS_ATTACKER_REF)" "$(TLS_ATTACKER_REPO)" "$(TLS_ATTACKER_SRC)"
	(cd "$(TLS_ATTACKER_SRC)" && mvn -q clean install -DskipTests=true)
	cp "$(TLS_ATTACKER_SRC)"/apps/*.jar .
	rm -rf lib && cp -r "$(TLS_ATTACKER_SRC)/apps/lib" .
	@echo "=== done -- rebuilt from $(TLS_ATTACKER_REF); diff against git history to confirm no drift ==="

clean:
	rm -rf $(RESULTS)
