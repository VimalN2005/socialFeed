#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

cd services/core_drf
python manage.py collectstatic --no-input || true
python manage.py migrate
