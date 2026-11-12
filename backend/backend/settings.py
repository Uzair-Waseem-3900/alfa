from pathlib import Path
from dotenv import load_dotenv
import os
from datetime import timedelta
from urllib.parse import urlparse, parse_qs
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
SECRET_KEY = os.getenv("SECRET_KEY")
# uvicorn backend.asgi:application --port 8000 --reload
# celery -A backend worker -Q agent -l info
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

# ---- B2B (rate-list sharing between our own softwares) ----
# This software only READS another software's rate list (consumer half of the
# b2b app). The two JSON maps are parsed (and a bad value ignored safely) by
# b2b.config, never here.
def env_bool(name, default=False):
    value = os.getenv(name)
    return default if value is None else value.strip().lower() == "true"

B2B_PROVIDER_ENABLED = env_bool("B2B_PROVIDER_ENABLED")
B2B_CONSUMER_ENABLED = env_bool("B2B_CONSUMER_ENABLED")
B2B_PARTNER_SECRETS = os.getenv("B2B_PARTNER_SECRETS", "")          # {"<provider name>": "<shared secret>"}
B2B_PARTNER_BASE_URLS = os.getenv("B2B_PARTNER_BASE_URLS", "")      # {"<provider name>": "<backend root URL>"}
B2B_PARTNER_TIMEOUT_SECONDS = os.getenv("B2B_PARTNER_TIMEOUT_SECONDS", "3")          # parsed safely by b2b.config
# Protects the endpoint a partner software calls (the "doorbell") — safe defaults, no env needed.
B2B_SIGNATURE_MAX_AGE_SECONDS = os.getenv("B2B_SIGNATURE_MAX_AGE_SECONDS", "60")
B2B_FAILED_AUTH_LIMIT = os.getenv("B2B_FAILED_AUTH_LIMIT", "10/hour")

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
    'b2b',
    'ai_agent',
]

INSTALLED_APPS += EXTERNAL_APPS

MIDDLEWARE = [
    # 'backend.middleware.ForceServerErrorMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
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

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


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
        "user": "120/minute",  # 120 requests per minute for authenticated users
        "agent": "20/minute",  # ai_agent: every run costs LLM calls (ScopedRateThrottle)
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



# Celery
# celery -A backend worker -l info
# celery -A backend worker -Q agent -l info
# import ssl
# # Add SSL configuration for Celery
# CELERY_BROKER_USE_SSL = {
#     'ssl_cert_reqs': ssl.CERT_REQUIRED  # or ssl.CERT_NONE for testing
# }
# CELERY_REDIS_BACKEND_USE_SSL = {
#     'ssl_cert_reqs': ssl.CERT_REQUIRED  # or ssl.CERT_NONE for testing
# }
REDIS_URL=os.getenv("REDIS_URL", "redis://127.0.0.1:6379")
CELERY_BROKER_URL         = f"{REDIS_URL}/0"
CELERY_RESULT_BACKEND     = f"{REDIS_URL}/0"
CELERY_WORKER_POOL        = "solo"
CELERY_ACCEPT_CONTENT     = ["application/json"]
CELERY_RESULT_SERIALIZER  = "json"
CELERY_TASK_SERIALIZER    = "json"
CELERY_TIMEZONE           = "Asia/Karachi"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT    = 30 * 60   # 30 minutes
CELERY_RESULT_EXPIRES     = 86400     # 1 day
CELERY_WORKER_POOL_RESTARTS = True
# ai_agent runs on its OWN queue so its (slow, LLM-bound) tasks never compete
# with other workers on the default "celery" queue, and can be scaled alone:
#   celery -A backend worker -Q agent -l info
CELERY_TASK_ROUTES = {"ai_agent.tasks.run_agent_task": {"queue": "agent"}}


# ---- ai_agent (business chat assistant) ----
# Gemini through its OpenAI-compatible endpoint (dev/free tier). GEMINI_API_KEY
# lives only in .env. Everything below is env-overridable, nothing hardcoded
# in app code.
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
AGENT_NAME      = os.getenv("AGENT_NAME", "Munshi")
AGENT_MODEL     = os.getenv("AGENT_MODEL", "gemini-2.5-flash")
AGENT_MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS", "8"))              # LLM round trips per question
AGENT_HISTORY_ITEM_LIMIT = int(os.getenv("AGENT_HISTORY_ITEM_LIMIT", "40"))  # session items fed back to the LLM
AGENT_TOOL_ROW_CAP = int(os.getenv("AGENT_TOOL_ROW_CAP", "25"))       # max rows any tool returns
AGENT_MAX_INPUT_CHARS = int(os.getenv("AGENT_MAX_INPUT_CHARS", "2000"))
AGENT_RUN_TIMEOUT_SECONDS = int(os.getenv("AGENT_RUN_TIMEOUT_SECONDS", "180"))  # hard cap for one answer
# Event stream (Redis Streams) — same Redis server as Celery, separate DB index
# and key prefix so broker data on /0 is untouched.
AGENT_REDIS_URL = f"{REDIS_URL}/1"
AGENT_STREAM_TTL_SECONDS = int(os.getenv("AGENT_STREAM_TTL_SECONDS", "3600"))
