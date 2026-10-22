#!/usr/bin/env bash

# Auto-detect and activate virtual environment on Azure App Service
if [ -f "/antenv/bin/activate" ]; then
    source /antenv/bin/activate
elif [ -f "antenv/bin/activate" ]; then
    source antenv/bin/activate
elif [ -f "/home/site/wwwroot/antenv/bin/activate" ]; then
    source /home/site/wwwroot/antenv/bin/activate
fi

# Run database migrations using root manage.py
python manage.py migrate --noinput || true

# Execute Gunicorn using root wsgi:application
exec python -m gunicorn wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120
