FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# DejaVu is the font the page-capture PDF renders with. ReportLab's built-in
# fonts cover Latin-1 only and draw a solid black box for anything outside it,
# and a captured web page routinely carries accents, curly quotes, arrows and
# currency marks. One megabyte buys a page that is readable instead.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

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
