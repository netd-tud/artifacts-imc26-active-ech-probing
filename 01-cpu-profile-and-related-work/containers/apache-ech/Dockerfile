# apache httpd alpine image with ECH support.
#
# Adapted from https://github.com/docker-library/httpd (2.4/alpine).
# Differences from upstream:
#   - httpd is built from the defo-project/apache-httpd fork (trunk = 2.5.x dev)
#     which carries the SSLECHKeyDir directive.
#   - linked against the defo-project OpenSSL ECH fork (openssl-3.4.1-ECH).
#   - the official entrypoint scripting / mod set is omitted; we bind-mount
#     our own httpd.conf in the test framework.
#
# Build args:
#   APACHE_REPO        git URL of an ECH-capable httpd fork
#   APACHE_REF         branch, tag, or commit SHA to check out. Pinned to a
#                      commit rather than tracking `trunk` (a moving branch)
#                      for reproducibility; override to track `trunk` again.
#   OPENSSL_ECH_REPO   git URL of an ECH-capable OpenSSL (defo fork)
#   OPENSSL_ECH_REF    branch or tag to clone
#   ALPINE_VERSION     alpine base image tag

ARG ALPINE_VERSION=3.20

# ---------------------------------------------------------------------------
# Builder stage
# ---------------------------------------------------------------------------
FROM alpine:${ALPINE_VERSION} AS builder

ARG OPENSSL_ECH_REPO=https://github.com/defo-project/openssl.git
ARG OPENSSL_ECH_REF=openssl-3.4.1-ECH
ARG APACHE_REPO=https://github.com/defo-project/apache-httpd.git
ARG APACHE_REF=0043400bb46cf0a6ef445e6fa0617710731c63d8

ARG OPENSSL_EXTRA_CFLAGS="-g -fno-omit-frame-pointer"
ARG HTTPD_CFLAGS="-O2 -g -fno-omit-frame-pointer"

RUN apk add --no-cache \
        build-base \
        linux-headers \
        apr-dev \
        apr-util-dev \
        pcre-dev \
        pcre2-dev \
        zlib-dev \
        expat-dev \
        nghttp2-dev \
        perl \
        wget \
        git \
        ca-certificates \
        autoconf \
        automake \
        libtool \
        python3

WORKDIR /src

RUN git clone --depth 1 --branch "${OPENSSL_ECH_REF}" "${OPENSSL_ECH_REPO}" openssl

WORKDIR /src/openssl
RUN ./Configure linux-x86_64 \
        --prefix=/opt/openssl \
        --openssldir=/opt/openssl/ssl \
        --libdir=lib \
        shared $OPENSSL_EXTRA_CFLAGS
RUN make -j"$(nproc)"
RUN make install_sw

ARG APR_REPO=https://github.com/apache/apr.git
ARG APR_REF=1.7.x
ARG APR_UTIL_REPO=https://github.com/apache/apr-util.git
ARG APR_UTIL_REF=1.6.x

WORKDIR /src
# `git clone --branch` only accepts a ref name (branch/tag), not a commit SHA.
# APACHE_REF is pinned to a commit for reproducibility, so this fetches it
# by SHA instead. GitHub allows shallow-fetching any reachable commit, not
# just ref tips, so --depth 1 still applies.
RUN mkdir apache-httpd \
 && cd apache-httpd \
 && git init -q \
 && git remote add origin "${APACHE_REPO}" \
 && git fetch -q --depth 1 origin "${APACHE_REF}" \
 && git checkout -q FETCH_HEAD
RUN git clone --depth 1 --branch "${APR_REF}"      "${APR_REPO}"      apache-httpd/srclib/apr
RUN git clone --depth 1 --branch "${APR_UTIL_REF}" "${APR_UTIL_REPO}" apache-httpd/srclib/apr-util

WORKDIR /src/apache-httpd
RUN ./buildconf
RUN ./configure \
        --prefix=/usr/local/apache2 \
        --with-included-apr \
        --enable-mpms-shared=event \
        --enable-ssl=shared \
        --with-ssl=/opt/openssl \
        --enable-mods-shared='unixd mime socache_shmcb authn_core authz_core' \
        CFLAGS="-I/opt/openssl/include $HTTPD_CFLAGS" \
        LDFLAGS="-L/opt/openssl/lib -Wl,-rpath,/opt/openssl/lib"
RUN make -j"$(nproc)"
RUN make install

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM alpine:${ALPINE_VERSION}

LABEL org.opencontainers.image.source="https://github.com/docker-library/httpd (adapted)"
LABEL org.opencontainers.image.description="apache httpd (defo fork) with ECH-capable OpenSSL (defo-project fork)"

RUN set -x \
 && (getent group www-data  >/dev/null 2>&1 || addgroup -g 82 -S www-data) \
 && (id -u www-data         >/dev/null 2>&1 || adduser -u 82 -D -S -G www-data www-data) \
 && apk add --no-cache apr apr-util pcre2 zlib expat ca-certificates tzdata \
 && mkdir -p /usr/local/apache2/logs

COPY --from=builder /usr/local/apache2 /usr/local/apache2
COPY --from=builder /opt/openssl/lib   /opt/openssl/lib

RUN ln -sf /dev/stdout /usr/local/apache2/logs/access_log \
 && ln -sf /dev/stderr /usr/local/apache2/logs/error_log

ENV PATH=/usr/local/apache2/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

EXPOSE 80
STOPSIGNAL SIGWINCH
CMD ["httpd", "-DFOREGROUND"]
