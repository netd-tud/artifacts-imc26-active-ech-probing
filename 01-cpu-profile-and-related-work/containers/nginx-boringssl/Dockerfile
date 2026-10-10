# nginx alpine image linked against Google BoringSSL.
#
# BoringSSL has ECH support at the library level.
 # However, the upstream nginx `ssl_ech_file` directive is defo-project's
# patch wired against the defo OpenSSL API, *not*
# BoringSSL's API.  This image therefore exposes ECH "compiled in but not
# configurable from nginx.conf"
#
# Build args:
#   NGINX_VERSION       e.g. 1.29.4
#   BORINGSSL_REPO      git URL of the BoringSSL fork
#   BORINGSSL_REF       branch or tag to clone
#   ALPINE_VERSION      alpine base image tag

ARG ALPINE_VERSION=3.20

# ---------------------------------------------------------------------------
# Builder stage
# ---------------------------------------------------------------------------
FROM alpine:${ALPINE_VERSION} AS builder

ARG BORINGSSL_REPO=https://github.com/google/boringssl.git
ARG BORINGSSL_REF=0.20260803.0

RUN apk add --no-cache \
        build-base \
        linux-headers \
        pcre2-dev \
        zlib-dev \
        perl \
        wget \
        git \
        ca-certificates \
        cmake \
        ninja \
        go

WORKDIR /src

# --- BoringSSL build --------------------------------------------------------
RUN git clone --depth 1 --branch "${BORINGSSL_REF}" "${BORINGSSL_REPO}" boringssl

WORKDIR /src/boringssl
RUN mkdir build \
 && cd build \
 && cmake -GNinja -DCMAKE_BUILD_TYPE=Release .. \
 && ninja ssl crypto

ARG NGINX_VERSION

WORKDIR /src
RUN wget -q "https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz" \
 && tar xzf "nginx-${NGINX_VERSION}.tar.gz"

WORKDIR /src/nginx-${NGINX_VERSION}

# `--with-openssl=` is not used here; that path invokes OpenSSL's own
# Configure script, which BoringSSL doesn't ship.  Instead we link the
# pre-built static archives via cc/ld opts.
RUN ./configure \
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
        --with-cc-opt="-I/src/boringssl/include -Wno-error" \
        --with-ld-opt="-L/src/boringssl/build -lssl -lcrypto -lpthread -lstdc++" \
 && make -j"$(nproc)" \
 && make install \
 && strip /usr/local/sbin/nginx

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM alpine:${ALPINE_VERSION}

LABEL org.opencontainers.image.source="https://github.com/nginx/docker-nginx (adapted)"
LABEL org.opencontainers.image.description="nginx linked against BoringSSL (ECH at library level)"

RUN set -x \
 && (getent group nginx >/dev/null 2>&1 || addgroup -g 101 -S nginx) \
 && (id -u nginx        >/dev/null 2>&1 || adduser -u 101 -D -S -G nginx -h /var/cache/nginx -s /sbin/nologin nginx) \
 && apk add --no-cache pcre2 zlib ca-certificates tzdata libstdc++ libgcc \
 && mkdir -p /var/log/nginx /var/cache/nginx \
 && ln -sf /dev/stdout /var/log/nginx/access.log \
 && ln -sf /dev/stderr /var/log/nginx/error.log

COPY --from=builder /usr/local/sbin/nginx /usr/local/sbin/nginx
COPY --from=builder /etc/nginx            /etc/nginx

EXPOSE 80
STOPSIGNAL SIGQUIT

CMD ["nginx", "-g", "daemon off;"]
