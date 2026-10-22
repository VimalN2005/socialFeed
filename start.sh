#!/usr/bin/env bash
python services/core_drf/manage.py migrate --noinput || true
exec gunicorn --chdir services/core_drf config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2

