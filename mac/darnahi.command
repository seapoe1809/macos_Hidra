#!/bin/bash
# Darnahi · Project Hidra — macOS launcher.
# Double-click in Finder, or run from Terminal:  ./mac/darnahi.command
# Starts the app and opens it in your default browser.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${HIDRA_PORT:-8000}"

# Guard: setup must have run.
if [ ! -x "hvenv/bin/uvicorn" ] || [ ! -f ".env" ]; then
  echo "✗ Not set up yet. Run first:  ./mac/setup.command"
  read -r -p "Press Return to close…" _ || true
  exit 1
fi

# Make sure Docker Desktop is up if we rely on the local DB container.
if command -v docker >/dev/null 2>&1; then
  if ! docker info >/dev/null 2>&1; then
    echo "⚠ Docker isn't running. Start Docker Desktop if you're using the bundled database."
  fi
fi

# Open the browser a moment after the server binds.
( sleep 2; open "http://localhost:${PORT}" >/dev/null 2>&1 || true ) &

# Reuse the shared launcher (starts the hidra-pg container + uvicorn).
exec ./darnahi
