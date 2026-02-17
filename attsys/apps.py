# attsys/apps.py
from django.apps import AppConfig
from django.contrib.auth import get_user_model
from django.db.utils import ProgrammingError, OperationalError
import os

class AttsysConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'attsys'

    def ready(self):
        # Skip if running migrations
        import sys
        if 'migrate' in sys.argv:
            return
            
        try:
            User = get_user_model()

            username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
            email = os.environ.get('DJANGO_SUPERUSER_EMAIL')
            password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

            if not username or not password:
                return

            # Check if table exists first by trying a simple query
            if not User.objects.filter(is_superuser=True).exists():
                User.objects.create_superuser(
                    username=username,
                    email=email,
                    password=password,
                    role='ADMIN'
                )
                print('✅ Superuser created automatically')
        except (ProgrammingError, OperationalError):
            # Database tables haven't been created yet (first migration)
            # Silently skip - superuser will be created after migrations
            pass