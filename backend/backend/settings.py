from pathlib import Path
from dotenv import load_dotenv
import os
from datetime import timedelta
from urllib.parse import urlparse, parse_qs
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
SECRET_KEY = os.getenv("SECRET_KEY")


DEBUG = os.getenv("DEBUG").lower() == "true"

def env_list(name):
    value = os.getenv(name)
    return [item.strip() for item in value.split(",")] if value else []

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
BACKEND_URL = os.getenv("BACKEND_URL").rstrip("/")
CUSTOMER_PREFIX = os.getenv("CUSTOMER_PREFIX")

PATH_ADMIN = os.getenv("PATH_ADMIN")
COMPANY_NAME=os.getenv("COMPANY_NAME")

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
]

EXTERNAL_APPS = [
    'users',
    'purchases',
    'rates',
    'billing',
    'cash_flow',
    'ledger',
    'reports',
    'data_entry',
    'taxes',
    'cash_management',
    'assets',
    'recurring_expenses',
    'profits',
    'backups',
    'credit_score',
    'activity_log',
    'accounting',
    'payment_methods',
    'sales_man',
]

INSTALLED_APPS += EXTERNAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    "corsheaders.middleware.CorsMiddleware",
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'activity_log.middleware.CurrentUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'



DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": os.getenv("DB_NAME"),
#         "USER": os.getenv("DB_USER"),
#         "PASSWORD": os.getenv("DB_PASSWORD"),
#         "HOST": os.getenv("DB_HOST"),
#         "PORT": os.getenv("DB_PORT"),
#         # Reuse a connection to the Supabase Session Pooler for 120s instead
#         # of paying a fresh TCP+TLS+auth handshake on every request (the
#         # dominant cost behind the ~6s customer-list load — see chat).
#         "CONN_MAX_AGE": 120,
#     }
# }


# Remote backup target (Supabase/Neon/any Postgres) — read from
# BACKUP_DATABASE in .env.local. Optional: if unset, the remote backup
# endpoints simply aren't usable (checked at request time in backups/services.py),
# local backups are unaffected either way.
BACKUP_DATABASE_URL = os.getenv("BACKUP_DATABASE")

if BACKUP_DATABASE_URL:
    _backup_db_parsed = urlparse(BACKUP_DATABASE_URL)
    _backup_db_query = parse_qs(_backup_db_parsed.query)
    DATABASES['backup_remote'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': _backup_db_parsed.path.lstrip('/'),
        'USER': _backup_db_parsed.username,
        'PASSWORD': _backup_db_parsed.password,
        'HOST': _backup_db_parsed.hostname,
        'PORT': _backup_db_parsed.port or 5432,
        'OPTIONS': {
            'sslmode': (_backup_db_query.get('sslmode') or ['require'])[0],
        },
    }



AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]



LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Karachi'

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# ---- Custom user model ----
AUTH_USER_MODEL = "users.User"
 
# ---- DRF settings ----
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "backend.paginations.StandardResultsSetPagination",
    "NUM_PROXIES": 1,  # Crucial for Server side: Tells DRF we're behind 1 proxy so it gets the real client IP, not server's internal IP
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle"
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/minute",   # 20 requests per minute for unauthenticated users
        "user": "120/minute"   # 120 requests per minute for authenticated users
    }
}
 
# ---- SimpleJWT settings ----

 
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),  #now for production
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7), #now for production
    "ROTATE_REFRESH_TOKENS": True,           # new refresh token on every refresh call
    "BLACKLIST_AFTER_ROTATION": True,        # old refresh token is blacklisted after rotation
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "email",               # our PK is email, not id
    "USER_ID_CLAIM": "user_email",
}


MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'



# Legacy source database — used by one-off data-import management commands
# (e.g. purchases.import_legacy_lookup_data) to read from the old DB and
# write into the new "default" DB. Not used for routine app traffic.
# DATA_GMAIL = os.getenv("DATA_GMAIL")
# if os.getenv("DB_NAME1"):
#     DATABASES["legacy"] = {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": os.getenv("DB_NAME1"),
#         "USER": os.getenv("DB_USER1"),
#         "PASSWORD": os.getenv("DB_PASSWORD1"),
#         "HOST": os.getenv("DB_HOST1"),
#         "PORT": os.getenv("DB_PORT1"),
#     }