#!/bin/sh
set -e

cd /app/financial_system
python manage.py migrate --noinput

exec gunicorn \
  --bind 0.0.0.0:8000 \
  --workers ${GUNICORN_WORKERS:-3} \
  --worker-class sync \
  --worker-connections 1000 \
  --timeout 30 \
  --keepalive 5 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --access-logfile - \
  --error-logfile - \
  financial_system.wsgi:application
