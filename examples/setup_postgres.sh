#!/usr/bin/env bash
# Spins up a local Postgres instance for DeepEcoHab dev/testing, using
# conda-installed binaries. No Docker, no system service, no sudo.
#
# This is a trust-authenticated, localhost-only dev database. Do not
# point it at anything other than your own machine.
#
# Usage:
#   ./setup_postgres.sh          # init (first run) + start, print the DSN
#   ./setup_postgres.sh stop     # stop the server
#   ./setup_postgres.sh status   # check whether it's running
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PGDATA="$REPO_ROOT/.pgdata"
PORT=5433
APP_USER=deepecohab
APP_PASSWORD=deepecohab
APP_DB=ecohab

if [[ "${1:-}" == "stop" ]]; then
    pg_ctl -D "$PGDATA" stop -m fast
    exit 0
fi

if [[ "${1:-}" == "status" ]]; then
    pg_ctl -D "$PGDATA" status
    exit 0
fi

if ! command -v pg_ctl >/dev/null 2>&1; then
    if [[ -z "${CONDA_DEFAULT_ENV:-}" ]]; then
        echo "pg_ctl not found and no conda env is active. Run 'conda activate <env>' first." >&2
        exit 1
    fi
    echo "Installing postgresql into conda env '$CONDA_DEFAULT_ENV'..."
    conda install -y -c conda-forge postgresql
fi

if [[ ! -d "$PGDATA" ]]; then
    echo "Initializing Postgres data directory at $PGDATA ..."
    # trust auth = fine for a localhost-only dev database, not for anything reachable
    # beyond this machine
    initdb -D "$PGDATA" -U "$(whoami)" --auth=trust
    sed -i "s/^#listen_addresses = 'localhost'/listen_addresses = 'localhost'/" "$PGDATA/postgresql.conf"
    sed -i "s/^#port = 5432/port = $PORT/" "$PGDATA/postgresql.conf"
fi

if ! pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
    pg_ctl -D "$PGDATA" -l "$PGDATA/server.log" start
fi

psql_admin() { psql -h localhost -p "$PORT" -d postgres -tAc "$1"; }

if [[ "$(psql_admin "SELECT 1 FROM pg_roles WHERE rolname='$APP_USER'")" != "1" ]]; then
    psql_admin "CREATE ROLE $APP_USER LOGIN PASSWORD '$APP_PASSWORD'" >/dev/null
fi
if [[ "$(psql_admin "SELECT 1 FROM pg_database WHERE datname='$APP_DB'")" != "1" ]]; then
    psql_admin "CREATE DATABASE $APP_DB OWNER $APP_USER" >/dev/null
fi

DSN="postgresql://$APP_USER:$APP_PASSWORD@localhost:$PORT/$APP_DB"
cat <<EOF

Postgres is running (data dir: $PGDATA).

  export ECOHAB_PG_DSN="$DSN"

Stop it any time with: $0 stop
EOF
