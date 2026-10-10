CONTAINERS ?= ../containers

PODMAN         ?= podman
ALPINE_VERSION ?= 3.20

# OpenSSL ECH fork (defo-project), shared by the nginx-ech and apache-ech
# images. Pinned to defo's 3.4.1 ECH branch
OPENSSL_ECH_REPO ?= https://github.com/defo-project/openssl.git
OPENSSL_ECH_REF  ?= openssl-3.4.1-ECH

# nginx-ech image (built from $(CONTAINERS)/nginx-ech/Dockerfile). The
# ssl_ech_file directive exists in nginx from 1.29.4 onwards.
NGINX_ECH_IMAGE  ?= localhost/nginx-ech
NGINX_TAG_SUFFIX ?= -alpine

# apache-ech image (built from $(CONTAINERS)/apache-ech/Dockerfile against the
# defo-project/apache-httpd fork; trunk carries the SSLECHKeyDir directive).
APACHE_ECH_IMAGE  ?= localhost/apache-ech
APACHE_TAG_SUFFIX ?= -alpine
APACHE_REPO       ?= https://github.com/defo-project/apache-httpd.git
APACHE_REF        ?= 0043400bb46cf0a6ef445e6fa0617710731c63d8

# nginx-boringssl image (built from $(CONTAINERS)/nginx-boringssl/Dockerfile).
NGINX_BORINGSSL_IMAGE ?= localhost/nginx-boringssl
BORINGSSL_REPO        ?= https://github.com/google/boringssl.git
BORINGSSL_REF         ?= 0.20260803.0

$(CONTAINERS)/nginx-ech/.built-%: $(CONTAINERS)/nginx-ech/Dockerfile
	@echo "=== Building $(NGINX_ECH_IMAGE):$*$(NGINX_TAG_SUFFIX) ==="
	$(PODMAN) build \
	    --build-arg NGINX_VERSION="$*" \
	    --build-arg ALPINE_VERSION="$(ALPINE_VERSION)" \
	    --build-arg OPENSSL_ECH_REPO="$(OPENSSL_ECH_REPO)" \
	    --build-arg OPENSSL_ECH_REF="$(OPENSSL_ECH_REF)" \
	    -t "$(NGINX_ECH_IMAGE):$*$(NGINX_TAG_SUFFIX)" \
	    $(CONTAINERS)/nginx-ech
	@touch $@

$(CONTAINERS)/apache-ech/.built-%: $(CONTAINERS)/apache-ech/Dockerfile
	@echo "=== Building $(APACHE_ECH_IMAGE):$*$(APACHE_TAG_SUFFIX) ==="
	$(PODMAN) build \
	    --build-arg ALPINE_VERSION="$(ALPINE_VERSION)" \
	    --build-arg OPENSSL_ECH_REPO="$(OPENSSL_ECH_REPO)" \
	    --build-arg OPENSSL_ECH_REF="$(OPENSSL_ECH_REF)" \
	    --build-arg APACHE_REPO="$(APACHE_REPO)" \
	    --build-arg APACHE_REF="$(APACHE_REF)" \
	    -t "$(APACHE_ECH_IMAGE):$*$(APACHE_TAG_SUFFIX)" \
	    $(CONTAINERS)/apache-ech
	@touch $@

$(CONTAINERS)/nginx-boringssl/.built-%: $(CONTAINERS)/nginx-boringssl/Dockerfile
	@echo "=== Building $(NGINX_BORINGSSL_IMAGE):$*$(NGINX_TAG_SUFFIX) (BoringSSL build is slow) ==="
	$(PODMAN) build \
	    --build-arg NGINX_VERSION="$*" \
	    --build-arg ALPINE_VERSION="$(ALPINE_VERSION)" \
	    --build-arg BORINGSSL_REPO="$(BORINGSSL_REPO)" \
	    --build-arg BORINGSSL_REF="$(BORINGSSL_REF)" \
	    -t "$(NGINX_BORINGSSL_IMAGE):$*$(NGINX_TAG_SUFFIX)" \
	    $(CONTAINERS)/nginx-boringssl
	@touch $@
