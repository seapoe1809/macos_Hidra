# Darnahi · Project Hidra — app image (FastAPI + static frontend).
FROM python:3.12-slim

# git: the python-nostr dependency installs straight from GitHub.
# build-essential: fallback for any dependency without a prebuilt wheel.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code (frontend is served by the same process).
COPY backend ./backend
COPY frontend ./frontend

# Uploaded bill attachments live here (mounted as a volume in compose).
RUN mkdir -p /app/bill_uploads

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
