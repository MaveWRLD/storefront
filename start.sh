#!/bin/sh
set -e

python manage.py collectstatic --noinput

exec opentelemetry-instrument gunicorn storefront.wsgi \
    --bind 0.0.0.0:"$PORT" \
    --workers 3 \
    --threads 2 \
    --worker-class gthread \
    --worker-tmp-dir /dev/shm \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
