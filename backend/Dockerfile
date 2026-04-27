## ── Stage 1: Builder ──────────────────────────────────────────────
FROM dockerhub.packages.vcfd.broadcom.net/python:3.11-slim AS builder

WORKDIR /build

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

## ── Stage 2: Runtime ─────────────────────────────────────────────
FROM dockerhub.packages.vcfd.broadcom.net/python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY backend/app/ ./app/
COPY backend/scripts/ ./scripts/
COPY shared/ ./shared/

EXPOSE 8000

CMD ["gunicorn", "app.main:app", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8000", \
     "--access-logfile", "-"]
