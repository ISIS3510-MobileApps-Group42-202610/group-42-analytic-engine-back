import os
import sys
from django.core.wsgi import get_wsgi_application
from django.core.management import call_command

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'analytics_backend.settings')

application = get_wsgi_application()

try:
    print("Iniciando auto-migración de base de datos...")
    call_command('migrate', interactive=False)
    print("Migración completada con éxito.")
except Exception as e:
    print(f"Error durante la migración: {e}", file=sys.stderr)
