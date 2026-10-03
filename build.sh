#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install --no-cache-dir -r requirements.txt

python services/core_drf/manage.py collectstatic --no-input || true
python services/core_drf/manage.py migrate
