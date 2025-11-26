#!/bin/bash

set -e

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn server on port ${PORT:-8000}..."
exec gunicorn myproject.wsgi:application \
  --bind 0.0.0.0:${PORT:-8000} \
  --workers 1 \
  --threads 3 \
  --timeout 120 \
  --max-requests 1000 \
  --max-requests-jitter 50 \
  --log-level info
