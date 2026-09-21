FROM python:3.11-slim

# Install tesseract for OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads outputs

EXPOSE 10000

# Generation streams for minutes, so the worker timeout is generous and
# threads let one long stream run without blocking the other requests.
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "600", \
     "--workers", "2", "--threads", "4", "--worker-class", "gthread", "app:app"]
