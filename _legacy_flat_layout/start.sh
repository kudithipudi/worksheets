#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start.sh – Bootstrap + launch Texas Worksheet Generator
# Usage: sudo -u www-data bash start.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$APP_DIR/venv"
SOCKET="$APP_DIR/worksheets.sock"

echo "==> Working directory: $APP_DIR"
cd "$APP_DIR"

# ── 1. Environment file check ─────────────────────────────────────────────────
if [[ ! -f "$APP_DIR/.env" ]]; then
    echo "ERROR: .env file not found. Copy .env.example and fill in your values:"
    echo "  cp $APP_DIR/.env.example $APP_DIR/.env"
    exit 1
fi

# ── 2. Create virtualenv if absent ───────────────────────────────────────────
if [[ ! -d "$VENV" ]]; then
    echo "==> Creating Python virtual environment..."
    python3 -m venv "$VENV"
fi

# ── 3. Install / upgrade dependencies ────────────────────────────────────────
echo "==> Installing dependencies..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# ── 4. Ensure static directory exists ────────────────────────────────────────
mkdir -p "$APP_DIR/static"

# ── 5. Remove stale Unix socket (prevents "address already in use" errors) ───
if [[ -S "$SOCKET" ]]; then
    echo "==> Removing stale socket: $SOCKET"
    rm -f "$SOCKET"
fi

# ── 6. Start Gunicorn ────────────────────────────────────────────────────────
echo "==> Starting Gunicorn on $SOCKET..."
exec "$VENV/bin/gunicorn" \
    --config "$APP_DIR/gunicorn_config.py" \
    main:app
