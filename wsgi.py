import os
import sys
from pathlib import Path

# Add services/core_drf to Python path so apps, common, config can be imported directly
BASE_DIR = Path(__file__).resolve().parent
CORE_DIR = BASE_DIR / 'services' / 'core_drf'
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
app = application

# Auto-run database migrations on boot so tables exist without manual commands
try:
    from django.core.management import call_command
    call_command('migrate', interactive=False)
except Exception as e:
    print(f"Startup migration notice: {e}")
