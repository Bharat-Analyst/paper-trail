# Dockerfile — OPTIONAL container build for PaperPilot.
#
# You DON'T need this if you deploy with render.yaml (native Python) — that's
# the simpler path in the README. This file is here in case you prefer Docker,
# or want to deploy somewhere that requires a container (Fly.io, Railway, etc.).
#
# Build & run locally:
#   docker build -t paperpilot .
#   docker run -p 8000:8000 --env-file .env paperpilot

FROM python:3.11-slim

# Don't buffer stdout (so logs show up immediately) and don't write .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first (this layer is cached unless requirements change).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app.
COPY . .

# Render (and most hosts) inject a $PORT env var. Default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Use shell form so $PORT expands at runtime.
CMD uvicorn app.main_api:app --host 0.0.0.0 --port ${PORT}
