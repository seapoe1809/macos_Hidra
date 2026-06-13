# macos_Hidra
Project Hidra in Mac

SEE https://github.com/seapoe1809/Hidra

# Darnahi · Project Hidra — macOS

Run the whole thing from the Terminal (or by double-clicking in Finder).

## Prerequisites

- **Python 3.10+** — `python3 --version`. If missing, install [Homebrew](https://brew.sh)
  then `brew install python`.
- **Docker Desktop** — https://www.docker.com/products/docker-desktop (used for the
  PostgreSQL database). Make sure it's **running** before setup.
  - Prefer your own Postgres? `brew install postgresql@16 && brew services start postgresql@16`,
    then set `HIDRA_DATABASE_URL` in `.env` and skip Docker.
- **git** — comes with the Xcode Command Line Tools (`xcode-select --install`).

## Run it

From the project root, in Terminal:

```bash
./mac/setup.command     # one-time: venv, dependencies, secrets, database
./mac/darnahi.command   # start the app (opens http://localhost:8000 automatically)
```

Or just **double-click** `mac/setup.command`, then `mac/darnahi.command` in Finder.

First time you double-click, macOS Gatekeeper may block it. Either:
- right-click the file → **Open** → **Open**, or
- make them executable once: `chmod +x mac/*.command`.

Stop the app with **Ctrl-C** in its Terminal window.

## What these do

- `setup.command` — checks Python/Docker, then runs the shared `setup.py` (creates
  `hvenv`, installs requirements, generates `.env` secrets, starts PostgreSQL, builds the
  schema).
- `darnahi.command` — starts the bundled database container if needed, launches the
  API + frontend, and runs `open http://localhost:8000`.

Both are thin macOS wrappers around the cross-platform `setup.py` and `darnahi` in the
project root, so there's a single source of truth.

## One-command alternative (Docker only)

If you'd rather not use the venv at all, the full stack runs in containers:

```bash
docker compose up -d --build
open http://localhost:8000
```

See the main [`README.md`](../README.md) for configuration and security notes.
