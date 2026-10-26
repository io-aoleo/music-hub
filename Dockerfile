# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM golang:1.25 AS engine-builder
ARG TARGETOS=linux
ARG TARGETARCH
ARG GOPROXY=https://proxy.golang.org,direct
ENV GOPROXY=$GOPROXY
WORKDIR /src
COPY vendor/go-music-dl/ ./
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -trimpath -o /music-dl ./cmd/music-dl
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata ffmpeg tini gosu && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=engine-builder /music-dl /usr/local/bin/music-dl
COPY app.py engine_client.py gateway.py auth.py hub_features.py storage.py download_queue.py search_providers.py qr_login.py ./
COPY scripts ./scripts
COPY templates ./templates
COPY static ./static
COPY LICENSE NOTICE ./
RUN useradd --uid 1000 --create-home hub && mkdir -p /data/tasks /data/engine /music /shared /home/hub/data && ln -s /music /home/hub/data/downloads && chown -R hub:hub /app /data /music /shared /home/hub && chmod -R u=rwX,go=rX /app
ENV TZ=Asia/Shanghai HUB_DATA_DIR=/data/tasks HUB_ENGINE_URL=http://127.0.0.1:9981 HUB_ENGINE_TOKEN_FILE=/shared/engine-token ENGINE_INTERNAL_TOKEN_FILE=/shared/engine-token MUSIC_DL_CONFIG_DB=/data/engine/settings.db MUSIC_DL_FAVORITES_DB=/data/engine/favorites.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=8s --start-period=60s --retries=3 CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=5)); assert d.get('engine') is True"
ENTRYPOINT ["/usr/bin/tini", "--", "sh", "/app/scripts/container-entrypoint.sh"]
