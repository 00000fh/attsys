from pathlib import Path
from decouple import config
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config(
    'SECRET_KEY',
    default='django-insecure-dev-key-only'
)

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = [
    'attsys.onrender.com',
    'localhost',
    '127.0.0.1',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

DATABASE_URL = config('DATABASE_URL', default=None)

if DATABASE_URL:
    DATABASES['default'] = dj_database_url.parse(DATABASE_URL)
