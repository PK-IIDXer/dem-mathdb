FROM node:22.23.4-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914 AS build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM caddy:2.11.7-builder@sha256:bf6a7d38add2508b7d2e3e3f40cf2af399214f143c0fa3daa51f254e01f8d293 AS caddy-build
ENV GOTOOLCHAIN=local GOSUMDB=sum.golang.org GOPROXY=https://proxy.golang.org
COPY deploy/beta/verify-web-security.sh /usr/local/bin/verify-web-security
# No extra modules; the pinned builder contains Go 1.27.3 and xcaddy 0.4.7.
RUN test "$(go env GOSUMDB)" = sum.golang.org \
    && test -z "$(go env GONOSUMDB)" \
    && test -z "$(go env GOPRIVATE)" \
    && test -z "$(go env GOINSECURE)" \
    && test -z "$(go env GOFLAGS)" \
    && xcaddy build v2.11.7 --replace golang.org/x/net=golang.org/x/net@v0.62.0 --output /usr/bin/caddy \
    && go version -m /usr/bin/caddy > /tmp/caddy-build-info \
    && cat /tmp/caddy-build-info \
    && sh /usr/local/bin/verify-web-security go "$(awk 'NR == 1 { sub(/^go/, "", $NF); print $NF }' /tmp/caddy-build-info)" \
    && sh /usr/local/bin/verify-web-security build-info /tmp/caddy-build-info v2.11.7 \
    && caddy build-info

FROM caddy:2.11.7-alpine@sha256:eb4d35b7452d1ab6171fbdbe8d9275b2301dad6dad92115d91e19fb9b24d510f
RUN apk add --no-cache 'ca-certificates>=20261020-r0' 'ca-certificates-bundle>=20261020-r0' \
    'curl>=8.23.0-r0' 'libcurl>=8.23.0-r0' 'brotli-libs>=1.2.1-r0' libssl3 libcrypto3 openssl \
    && test "$(apk version -t "$(apk info -v ca-certificates | sed 's/^ca-certificates-//')" 20261020-r0)" != '<' \
    && test "$(apk version -t "$(apk info -v ca-certificates-bundle | sed 's/^ca-certificates-bundle-//')" 20261020-r0)" != '<' \
    && test "$(apk version -t "$(apk info -v curl | sed 's/^curl-//')" 8.23.0-r0)" != '<' \
    && test "$(apk version -t "$(apk info -v libcurl | sed 's/^libcurl-//')" 8.23.0-r0)" != '<' \
    && test "$(apk version -t "$(apk info -v brotli-libs | sed 's/^brotli-libs-//')" 1.2.1-r0)" != '<'
COPY deploy/beta/verify-web-security.sh /usr/local/bin/verify-web-security
COPY --from=caddy-build /usr/bin/caddy /usr/bin/caddy
RUN sh /usr/local/bin/verify-web-security ca /etc/ssl/certs/ca-certificates.crt \
    && apk del --no-cache openssl \
    && ! apk info -e openssl \
    && ! command -v openssl \
    && apk info -e libssl3 \
    && apk info -e libcrypto3 \
    && caddy version
COPY --from=build /build/dist /srv
COPY deploy/beta/Caddyfile /etc/caddy/Caddyfile
COPY deploy/beta/maintenance.html /maintenance/maintenance.html
