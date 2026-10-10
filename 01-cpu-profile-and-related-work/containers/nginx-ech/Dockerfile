# nginx alpine image with ECH support.
#
# Adapted from https://github.com/nginx/docker-nginx (mainline/alpine-slim).
# Differences:
#   - nginx is built FROM SOURCE so it can be statically linked against
#     the defo-project OpenSSL ECH fork. 
#   - The official docker-entrypoint.sh / templating layer is omitted;
#     we bind-mount nginx.conf in the test framework
#
# Build args:
#   NGINX_VERSION        e.g. 1.29.4 (must be >= 1.29.4 for the
#                        ssl_ech_file directive to exist in stock nginx sources)
#   OPENSSL_ECH_REPO     git URL of an ECH-capable OpenSSL (defo fork)
#   OPENSSL_ECH_REF      branch or tag to clone
#   ALPINE_VERSION       alpine base image tag

ARG ALPINE_VERSION=3.20

# ---------------------------------------------------------------------------
# Builder stage
# ---------------------------------------------------------------------------
FROM alpine:${ALPINE_VERSION} AS builder

ARG OPENSSL_ECH_REPO=https://github.com/defo-project/openssl.git
ARG OPENSSL_ECH_REF=openssl-3.4.1-ECH

RUN apk add --no-cache \
        build-base \
        linux-headers \
        pcre2-dev \
        zlib-dev \
        perl \
        wget \
        git \
        ca-certificates

WORKDIR /src

RUN git clone --depth 1 --branch "${OPENSSL_ECH_REF}" "${OPENSSL_ECH_REPO}" openssl

ARG NGINX_VERSION

# Built with debug symbols and frame pointers by default so perf can resolve
# nginx symbols and walk frame-pointer call stacks .
#   NGINX_CC_OPT       extra C flags for nginx itself.
#   NGINX_STRIP        1 = strip the binary (smaller image, no perf symbols);
#                      0 = keep symbols (default).
#   NGINX_OPENSSL_OPT  extra options passed to the bundled OpenSSL's build via
#                      nginx's --with-openssl-opt. Frame pointers here too:
#                      without this, perf cannot unwind call graphs through
#                      OpenSSL (the ECH/HPKE path shows only as flat leaf
#                      symbols, not a call tree).
ARG NGINX_CC_OPT="-O2 -g -fno-omit-frame-pointer"
ARG NGINX_STRIP=0
ARG NGINX_OPENSSL_OPT="-g -fno-omit-frame-pointer"

RUN wget -q "https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz" \
 && tar xzf "nginx-${NGINX_VERSION}.tar.gz"

WORKDIR /src/nginx-${NGINX_VERSION}

# --with-openssl=<dir> tells nginx to build that OpenSSL source tree inline
# and static-link against it. The resulting nginx binary embeds ECH-capable
# OpenSSL
RUN set -eux; \
    set -- \
        --prefix=/usr/local/nginx \
        --sbin-path=/usr/local/sbin/nginx \
        --conf-path=/etc/nginx/nginx.conf \
        --error-log-path=/var/log/nginx/error.log \
        --http-log-path=/var/log/nginx/access.log \
        --pid-path=/var/run/nginx.pid \
        --lock-path=/var/run/nginx.lock \
        --http-client-body-temp-path=/var/cache/nginx/client_temp \
        --http-proxy-temp-path=/var/cache/nginx/proxy_temp \
        --http-fastcgi-temp-path=/var/cache/nginx/fastcgi_temp \
        --http-uwsgi-temp-path=/var/cache/nginx/uwsgi_temp \
        --http-scgi-temp-path=/var/cache/nginx/scgi_temp \
        --user=nginx --group=nginx \
        --with-http_ssl_module \
        --with-http_v2_module \
        --with-pcre-jit \
        --with-cc-opt="$NGINX_CC_OPT" \
        --with-openssl=/src/openssl; \
    if [ -n "$NGINX_OPENSSL_OPT" ]; then set -- "$@" --with-openssl-opt="$NGINX_OPENSSL_OPT"; fi; \
    ./configure "$@"; \
    make -j"$(nproc)"; \
    make install; \
    if [ "$NGINX_STRIP" = "1" ]; then strip /usr/local/sbin/nginx; fi

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM alpine:${ALPINE_VERSION}

LABEL org.opencontainers.image.source="https://github.com/nginx/docker-nginx (adapted)"
LABEL org.opencontainers.image.description="nginx with ECH-capable OpenSSL (defo-project fork)"

RUN set -x \
 && addgroup -g 101 -S nginx \
 && adduser -S -D -H -u 101 -h /var/cache/nginx -s /sbin/nologin -G nginx -g nginx nginx \
 && apk add --no-cache pcre2 zlib ca-certificates tzdata \
 && mkdir -p /var/log/nginx /var/cache/nginx \
 && ln -sf /dev/stdout /var/log/nginx/access.log \
 && ln -sf /dev/stderr /var/log/nginx/error.log

COPY --from=builder /usr/local/sbin/nginx /usr/local/sbin/nginx
COPY --from=builder /etc/nginx            /etc/nginx

EXPOSE 80
STOPSIGNAL SIGQUIT

CMD ["nginx", "-g", "daemon off;"]
