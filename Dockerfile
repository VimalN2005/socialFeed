FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project repository (including services, frontend, config)
COPY . /app/

# Collect static files
RUN python services/core_drf/manage.py collectstatic --no-input || true

EXPOSE 10000

# Automatically run database migrations and start Gunicorn on Render's dynamic $PORT
CMD ["sh", "-c", "python services/core_drf/manage.py migrate && exec gunicorn --chdir services/core_drf config.wsgi:application --bind 0.0.0.0:${PORT:-10000} --workers 2"]
