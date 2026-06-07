#!/usr/bin/env bash
set -e

BACKEND_DIR="$(cd "$(dirname "$0")/backend" && pwd)"
FRONTEND_DIR="$(cd "$(dirname "$0")/frontend" && pwd)"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

cmd="${1:-help}"

case "$cmd" in
  setup)
    echo "==> Installing backend dependencies..."
    cd "$BACKEND_DIR"
    python3 -m venv .venv
    # Bootstrap pip if ensurepip is unavailable (e.g. Debian/Ubuntu stripped venv)
    if ! .venv/bin/python3 -m pip --version &>/dev/null; then
      echo "  Bootstrapping pip via get-pip.py..."
      curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python3
    fi
    .venv/bin/pip install -q --upgrade pip setuptools wheel
    .venv/bin/pip install -q -e ".[dev]"

    echo "==> Running database migrations..."
    .venv/bin/alembic upgrade head

    echo "==> Seeding RSS sources..."
    .venv/bin/python scripts/seed_sources.py

    echo "==> Installing frontend dependencies..."
    cd "$FRONTEND_DIR"
    npm install

    echo ""
    echo "Setup complete. Run: ./start.sh dev"
    ;;

  migrate)
    cd "$BACKEND_DIR"
    .venv/bin/alembic upgrade head
    ;;

  api)
    cd "$BACKEND_DIR"
    .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --timeout-graceful-shutdown 3
    ;;

  ui)
    cd "$FRONTEND_DIR"
    npm run dev
    ;;

  dev)
    echo "==> Starting API on :8000 and UI on :5173"
    cd "$BACKEND_DIR" && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
    API_PID=$!

    cd "$FRONTEND_DIR" && npm run dev &
    UI_PID=$!

    echo "API PID: $API_PID  |  UI PID: $UI_PID"
    echo "Press Ctrl-C to stop both."
    trap "kill $API_PID $UI_PID 2>/dev/null; exit" INT TERM
    wait
    ;;

  stop)
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    echo "Stopped."
    ;;

  reset-db)
    echo "Dropping and recreating database..."
    cd "$BACKEND_DIR"
    rm -f cti.db
    .venv/bin/alembic upgrade head
    .venv/bin/python scripts/seed_sources.py
    echo "Done."
    ;;

  *)
    echo "Usage: ./start.sh <command>"
    echo ""
    echo "Commands:"
    echo "  setup      Install deps, run migrations, seed sources"
    echo "  dev        Start API + UI in background (dev mode)"
    echo "  api        Start API only (with reload)"
    echo "  ui         Start frontend only"
    echo "  migrate    Run pending Alembic migrations"
    echo "  stop       Kill running dev processes"
    echo "  reset-db   Drop and recreate local SQLite DB"
    ;;
esac
