#!/bin/bash
# Darnahi · Project Hidra — macOS first-run setup.
# Double-click in Finder, or run from Terminal:  ./mac/setup.command
set -euo pipefail

# Resolve the project root (parent of this mac/ folder) and work from there.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo "  Darnahi · Project Hidra — setup (macOS)"
echo "============================================================"

# --- Python 3.10+ ----------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "✗ python3 not found."
  echo "  Install Homebrew (https://brew.sh) then:  brew install python"
  exit 1
fi
PYV="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
echo "  Python ${PYV} detected."

# --- Docker (for the database) --------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "⚠ Docker not found."
  echo "  Install Docker Desktop: https://www.docker.com/products/docker-desktop"
  echo "  …or set HIDRA_DATABASE_URL in .env to point at your own PostgreSQL"
  echo "    (e.g. Homebrew:  brew install postgresql@16 && brew services start postgresql@16)."
  echo
elif ! docker info >/dev/null 2>&1; then
  echo "⚠ Docker is installed but not running — start Docker Desktop, then re-run this."
  echo
fi

# --- Run the cross-platform installer -------------------------------------
python3 setup.py

echo
echo "✓ Setup complete. Start the app by double-clicking:  mac/darnahi.command"
echo "  (or from Terminal:  ./mac/darnahi.command )"
echo
# Keep the Terminal window open when launched via double-click.
read -r -p "Press Return to close this window…" _ || true
