FROM python:3.11-slim

WORKDIR /app

COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Shared library + agent code (build context is the repo root)
COPY common/ /app/common/
COPY agent/ /app/

ENV PORT=8080
EXPOSE 8080

CMD ["python", "main.py"]
