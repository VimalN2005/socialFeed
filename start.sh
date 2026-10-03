#!/usr/bin/env bash
cd services/core_drf
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 2
