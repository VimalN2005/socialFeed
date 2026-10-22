#!/usr/bin/env python
import os
import sys
from pathlib import Path

def main():
    BASE_DIR = Path(__file__).resolve().parent
    CORE_DIR = BASE_DIR / 'services' / 'core_drf'
    if str(CORE_DIR) not in sys.path:
        sys.path.insert(0, str(CORE_DIR))

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
