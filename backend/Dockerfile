# ===== Stage 1: Builder =====
# Base Alpine + toolchain para compilar qualquer wheel sem build musllinux pronto.
FROM python:3.10-alpine AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apk add --no-cache --virtual .build-deps \
        gcc musl-dev libffi-dev postgresql-dev

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# ===== Stage 2: Runtime =====
# Imagem final Alpine mínima. libpq presente para o psycopg2 em runtime.
FROM python:3.10-alpine

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GUNICORN_WORKERS=3 \
    PATH="/opt/venv/bin:$PATH"

RUN apk add --no-cache libpq

COPY --from=builder /opt/venv /opt/venv
COPY . .

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
