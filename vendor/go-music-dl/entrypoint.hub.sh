#!/bin/sh
set -eu
if [ -n "${ENGINE_INTERNAL_TOKEN_FILE:-}" ]; then
    ENGINE_INTERNAL_TOKEN="$(cat "$ENGINE_INTERNAL_TOKEN_FILE")"
    export ENGINE_INTERNAL_TOKEN
fi
# 新安装默认下载目录仍沿用上游路径，但实际音乐写入独立挂载卷。
mkdir -p /home/appuser/data
if [ ! -e /home/appuser/data/downloads ] && [ ! -L /home/appuser/data/downloads ]; then
    ln -s /music /home/appuser/data/downloads
fi
exec ./music-dl web --port 9981 --no-browser
