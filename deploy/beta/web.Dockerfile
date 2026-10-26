FROM node:22.15.0-alpine AS build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
FROM caddy:2.10.2-alpine
COPY --from=build /build/dist /srv
COPY deploy/beta/Caddyfile /etc/caddy/Caddyfile
COPY deploy/beta/maintenance.html /maintenance/maintenance.html
