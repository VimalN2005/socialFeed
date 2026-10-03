#!/usr/bin/env bash
exec gunicorn --chdir services/core_drf config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 2
