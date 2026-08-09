FROM python:3.12-slim AS base

WORKDIR /app

# System deps for psycopg2, Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc libjpeg62-turbo-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --no-cache-dir -e .

# Non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Default: run the API via gunicorn
CMD ["gunicorn", "-c", "gunicorn.conf.py", "mediaforge.gateway.main:app"]

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/health')"
