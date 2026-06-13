#!/usr/bin/env python3
"""Darnahi · Project Hidra — first-run setup.

NOT a setuptools script — it's a one-shot installer you run once after cloning:

    python3 setup.py

It is idempotent (safe to re-run) and will:
  1. check the Python version,
  2. create the `hvenv` virtualenv and install requirements,
  3. generate a `.env` with strong secrets (provider token + DB password),
  4. provision PostgreSQL (a local Docker container by default),
  5. create the database tables.

Then start the app any time with:  ./darnahi
"""

import os
import secrets
import socket
import subprocess
import sys
import time
import venv

ROOT = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(ROOT, "hvenv")
PYBIN = os.path.join(VENV, "bin", "python")            # POSIX layout
ENV_FILE = os.path.join(ROOT, ".env")
REQS = os.path.join(ROOT, "requirements.txt")

PG_CONTAINER = "hidra-pg"
PG_PORT = 5433
PG_USER = "hidra"
PG_DB = "hidra"


def step(msg):
    print(f"\n\033[1m▶ {msg}\033[0m")


def info(msg):
    print(f"  {msg}")


def die(msg):
    print(f"\n\033[31m✗ {msg}\033[0m")
    sys.exit(1)


def have(cmd):
    from shutil import which
    return which(cmd) is not None


# --- 1. Python version -----------------------------------------------------
def check_python():
    step("Checking Python")
    if sys.version_info < (3, 10):
        die(f"Python 3.10+ required (found {sys.version.split()[0]}).")
    info(f"Python {sys.version.split()[0]} ✓")


# --- 2. virtualenv + deps --------------------------------------------------
def ensure_venv():
    step("Creating virtualenv (hvenv)")
    if os.path.exists(PYBIN):
        info("hvenv already exists ✓")
    else:
        venv.create(VENV, with_pip=True)
        info("created ✓")

    step("Installing dependencies (this can take a few minutes)")
    subprocess.check_call([PYBIN, "-m", "pip", "install", "--upgrade", "pip", "-q"])
    subprocess.check_call([PYBIN, "-m", "pip", "install", "-r", REQS, "-q"])
    info("dependencies installed ✓")


# --- 3. .env / secrets -----------------------------------------------------
def read_env():
    env = {}
    if os.path.isfile(ENV_FILE):
        for line in open(ENV_FILE, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def ensure_env():
    step("Generating secrets (.env)")
    if os.path.isfile(ENV_FILE):
        info(".env already exists — keeping existing secrets ✓")
        return read_env()

    db_pass = secrets.token_urlsafe(24)
    provider_token = secrets.token_urlsafe(24)
    database_url = f"postgresql://{PG_USER}:{db_pass}@127.0.0.1:{PG_PORT}/{PG_DB}"
    content = f"""# Darnahi · Project Hidra — environment (KEEP SECRET, do not commit)
# Regenerate by deleting this file and re-running setup.py.

# Master dashboard login token (each provider also gets its own).
HIDRA_PROVIDER_TOKEN={provider_token}

# PostgreSQL connection.
HIDRA_DATABASE_URL={database_url}

# Verify relay TLS certificates (leave false).
HIDRA_RELAY_INSECURE_SSL=false

# Extra CORS origins (blank = same-origin only).
HIDRA_CORS_ORIGINS=
"""
    with open(ENV_FILE, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.chmod(ENV_FILE, 0o600)
    info(f".env written (provider token + DB password generated) ✓")
    return read_env()


# --- 4. PostgreSQL ---------------------------------------------------------
def db_reachable(database_url):
    code = (
        "import sys, psycopg\n"
        "try:\n"
        "    psycopg.connect(sys.argv[1], connect_timeout=3).close()\n"
        "    print('OK')\n"
        "except Exception:\n"
        "    print('ERR')\n"
    )
    out = subprocess.run([PYBIN, "-c", code, database_url],
                         capture_output=True, text=True).stdout
    return "OK" in out


def container_exists():
    out = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True, text=True).stdout.splitlines()
    return PG_CONTAINER in out


def ensure_postgres(env):
    step("Provisioning PostgreSQL")
    database_url = env.get("HIDRA_DATABASE_URL", "")
    if db_reachable(database_url):
        info("database reachable ✓")
        return

    if not have("docker"):
        die("PostgreSQL is not reachable and Docker is not installed.\n"
            "  Install Docker, or point HIDRA_DATABASE_URL in .env at your own Postgres,\n"
            "  then re-run: python3 setup.py")

    # Derive the password from the DATABASE_URL we generated.
    db_pass = database_url.split("://", 1)[1].split(":", 1)[1].split("@", 1)[0]

    if container_exists():
        info(f"starting existing '{PG_CONTAINER}' container…")
        subprocess.run(["docker", "start", PG_CONTAINER],
                       capture_output=True, text=True)
    else:
        info(f"launching postgres:16 as '{PG_CONTAINER}' on port {PG_PORT}…")
        r = subprocess.run([
            "docker", "run", "-d", "--name", PG_CONTAINER, "--restart", "unless-stopped",
            "-e", f"POSTGRES_USER={PG_USER}", "-e", f"POSTGRES_PASSWORD={db_pass}",
            "-e", f"POSTGRES_DB={PG_DB}", "-p", f"{PG_PORT}:5432", "postgres:16",
        ], capture_output=True, text=True)
        if r.returncode != 0:
            die(f"docker run failed:\n{r.stderr}")

    info("waiting for the database to accept connections…")
    for _ in range(30):
        if db_reachable(database_url):
            info("database ready ✓")
            return
        time.sleep(1)
    die("Database did not become ready in time. Check: docker logs " + PG_CONTAINER)


# --- 5. schema -------------------------------------------------------------
def init_db():
    step("Creating database tables")
    subprocess.check_call(
        [PYBIN, "-c", "from backend import db; db.init_db()"], cwd=ROOT)
    info("schema ready ✓")


def main():
    print("=" * 60)
    print("  Darnahi · Project Hidra — setup")
    print("=" * 60)
    check_python()
    ensure_venv()
    env = ensure_env()
    ensure_postgres(env)
    init_db()
    print("\n\033[32m✓ Setup complete.\033[0m  Start the app with:\n")
    print("    ./darnahi\n")
    print("Then open http://localhost:8000 — set up a Provider first.")
    print("Your dashboard master token is in .env (HIDRA_PROVIDER_TOKEN).\n")


if __name__ == "__main__":
    main()
