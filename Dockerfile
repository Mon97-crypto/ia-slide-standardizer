FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default location of the SQLite library. Mount a Render disk here so the
# library survives deploys; without a disk the container filesystem is
# ephemeral and every deploy starts empty.
ENV CIQ_DB_PATH=/data/library.db
RUN mkdir -p /data

EXPOSE 10000

# Shell form so $PORT expands. Render injects PORT and routes to it, so a
# hardcoded bind means the health check never passes.
# --preload shares the loaded app across workers and surfaces import errors at
# boot rather than on the first request.
CMD gunicorn --bind "0.0.0.0:${PORT:-10000}" --workers 2 --threads 4 \
    --timeout 180 --preload app:app
