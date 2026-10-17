FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY data_pipeline/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared library + worker code (build context is the repo root)
COPY common/ /app/common/
COPY data_pipeline/ /app/

EXPOSE 8080

CMD ["uvicorn", "ingest_worker:app", "--host", "0.0.0.0", "--port", "8080"]
