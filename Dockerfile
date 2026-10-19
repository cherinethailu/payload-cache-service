FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PAYLOAD_CACHE_DATABASE_URL=sqlite:////data/payload_cache.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[postgres]"

# Run unprivileged; /data holds the SQLite database and is meant to be a volume.
RUN useradd --system --uid 10001 app && mkdir /data && chown app /data
USER app
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "payload_cache.main:app", "--host", "0.0.0.0", "--port", "8000"]
