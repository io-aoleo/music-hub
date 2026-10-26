#!/bin/sh
set -eu
if [ "$(id -u)" = 0 ]; then
    python /app/scripts/bootstrap.py
    exec gosu hub python /app/scripts/run_services.py
fi
exec python /app/scripts/run_services.py
