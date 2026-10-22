#!/usr/bin/env bash

# Auto-detect and activate virtual environment on Azure App Service
if [ -f "/antenv/bin/activate" ]; then
    source /antenv/bin/activate
elif [ -f "antenv/bin/activate" ]; then
    source antenv/bin/activate
elif [ -f "/home/site/wwwroot/antenv/bin/activate" ]; then
    source /home/site/wwwroot/antenv/bin/activate
fi

# Run database migrations
python services/core_drf/manage.py migrate --noinput || true

# Execute Gunicorn through Python module resolver
exec python -m gunicorn --chdir services/core_drf config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2


