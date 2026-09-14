"""
Single, environment-driven settings module.

There is deliberately no base/dev/prod split. Everything is read from the
environment, and every external service degrades to a zero-dependency local
default when its URL is unset:

    DATABASE_URL unset -> SQLite file
    REDIS_URL    unset -> in-memory channel layer + eager Celery

DEBUG has no default: it must come from `.env` (copy `.env.example`) or the
environment, so a deploy that forgets to configure anything fails at startup
instead of silently running in debug mode. The one exception is `pytest`,
which defaults to DEBUG=True so the test suite runs on a bare clone. See
docs/CONFIGURATION.md for the full variable reference.
"""

import sys
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# --------------------------------------------------------------------------
# Project identity
#
# The Python package stays `config` forever. Everything user-visible is driven
# by these, so cloning this template means editing .env, not renaming modules.
# --------------------------------------------------------------------------
PROJECT_NAME = env("PROJECT_NAME", default="Django Backend Template")
PROJECT_SLUG = env("PROJECT_SLUG", default="backend")
PROJECT_DESCRIPTION = env("PROJECT_DESCRIPTION", default="")

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
try:
    DEBUG = env.bool("DEBUG", default=True if "pytest" in sys.modules else env.NOTSET)
except ImproperlyConfigured:
    raise ImproperlyConfigured(
        "DEBUG must be set explicitly -- there is no default. Copy "
        ".env.example to .env (DEBUG=True there), or set DEBUG=False plus "
        "SECRET_KEY, ALLOWED_HOSTS, FRONTEND_URL and COOKIE_DOMAIN in "
        "production. See docs/CONFIGURATION.md."
    ) from None
SECRET_KEY = env("SECRET_KEY", default="dev-insecure-key-change-me" if DEBUG else "")
if not DEBUG and not SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY must be set when DEBUG is off. Generate one with:\n"
        '  python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"])

ROOT_URLCONF = "config.urls"
# Move the admin off the default path in production by setting ADMIN_URL.
ADMIN_URL = env("ADMIN_URL", default="admin/")
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Third party
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    "channels",
    "django_celery_beat",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.usersessions",
    "allauth.headless",
    # Local
    "apps.core",
    "apps.users",
    "apps.realtime",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "allauth.usersessions.middleware.UserSessionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

SITE_ID = 1

# --------------------------------------------------------------------------
# Database: SQLite unless DATABASE_URL points somewhere else.
# --------------------------------------------------------------------------
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}
if not DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

# --------------------------------------------------------------------------
# Redis-backed services. All optional in development.
# --------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# Sessions live in the cache when Redis is available (revocation checks stay off
# Postgres); otherwise in the database so they survive a dev-server restart.
SESSION_ENGINE = (
    "django.contrib.sessions.backends.cache" if REDIS_URL else "django.contrib.sessions.backends.db"
)

# --------------------------------------------------------------------------
# Celery. Without a broker, tasks run inline so nothing silently no-ops.
# --------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=not CELERY_BROKER_URL)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = env("TIME_ZONE", default="UTC")
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# --------------------------------------------------------------------------
# Frontend origin + cookie scope
#
# The Next.js app and this API are expected to share a parent domain
# (chat.example.edu / chat-api.example.edu). Same-site means a Lax session
# cookie is sent on API calls; cross-origin means we still need CORS.
# --------------------------------------------------------------------------
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:3000")
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[FRONTEND_URL])
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[FRONTEND_URL])

# Which Origins may open a WebSocket. This is the *frontend's* origin, which is
# not the same as ALLOWED_HOSTS (this API's own hostnames) -- see config/asgi.py.
WEBSOCKET_ALLOWED_ORIGINS = env.list(
    "WEBSOCKET_ALLOWED_ORIGINS",
    default=CORS_ALLOWED_ORIGINS + ALLOWED_HOSTS,
)

SESSION_COOKIE_NAME = env("SESSION_COOKIE_NAME", default=f"{PROJECT_SLUG}_sessionid")
SESSION_COOKIE_DOMAIN = env("COOKIE_DOMAIN", default=None) or None
CSRF_COOKIE_DOMAIN = SESSION_COOKIE_DOMAIN
SESSION_COOKIE_SAMESITE = env("COOKIE_SAMESITE", default="Lax")
CSRF_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE
SESSION_COOKIE_SECURE = env.bool("COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # the frontend must read it to send X-CSRFToken
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=60 * 60 * 24 * 14)

# --------------------------------------------------------------------------
# Feature flags. Read these through apps.core.flags, never directly.
# --------------------------------------------------------------------------
SIGNUP_ENABLED = env.bool("SIGNUP_ENABLED", default=True)
SIGNUP_REQUIRES_ACCESS_CODE = env.bool("SIGNUP_REQUIRES_ACCESS_CODE", default=False)

# When True, the API says "that email exists, and it uses Google". Friendlier,
# but it confirms account existence to anonymous callers. When False, allauth's
# enumeration-resistant path is used instead: signup appears to succeed and an
# "account already exists" email is sent. That path needs working email.
AUTH_DISCLOSE_ACCOUNT_EXISTENCE = env.bool("AUTH_DISCLOSE_ACCOUNT_EXISTENCE", default=True)

# --------------------------------------------------------------------------
# Authentication (django-allauth, headless)
# --------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_ADAPTER = "apps.users.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "apps.users.adapters.SocialAccountAdapter"
# allauth mixes this in as a base of its signup form, so the access_code field
# reaches the headless endpoint and the generated OpenAPI spec.
ACCOUNT_SIGNUP_FORM_CLASS = "apps.users.forms.SignupExtraFieldsForm"

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_PREVENT_ENUMERATION = not AUTH_DISCLOSE_ACCOUNT_EXISTENCE

# none | optional | mandatory. Ships as "none" so a fresh clone needs no SMTP.
# Google logins are pre-verified regardless of this setting.
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="none")
ACCOUNT_EMAIL_SUBJECT_PREFIX = f"[{PROJECT_NAME}] "
ACCOUNT_RATE_LIMITS = {"login_failed": "5/5m/ip,5/5m/key"}

# One email address = one authentication method. A Google login for an address
# that already has a password account is rejected rather than auto-linked;
# see apps/users/adapters.py and docs/AUTHENTICATION.md.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": env("GOOGLE_CLIENT_ID", default=""),
            "secret": env("GOOGLE_CLIENT_SECRET", default=""),
            "key": "",
        },
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        # Trust Google's email_verified claim, so Google signups skip verification.
        "VERIFIED_EMAIL": True,
    }
}

HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("browser",)
HEADLESS_SERVE_SPECIFICATION = True
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/auth/verify-email/{{key}}",
    "account_reset_password": f"{FRONTEND_URL}/auth/password/reset",
    "account_reset_password_from_key": f"{FRONTEND_URL}/auth/password/reset/{{key}}",
    "account_signup": f"{FRONTEND_URL}/auth/signup",
    "socialaccount_login_error": f"{FRONTEND_URL}/auth/callback",
}

USERSESSIONS_TRACK_ACTIVITY = True

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": env.int("PASSWORD_MIN_LENGTH", default=10)},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Email. Console backend in development: verification and reset links are
# printed to the terminal, so no mail server is needed to exercise the flows.
# --------------------------------------------------------------------------
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@localhost")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --------------------------------------------------------------------------
# DRF + OpenAPI. The schema is the contract for the separate frontend repo.
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
if DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(
        "rest_framework.renderers.BrowsableAPIRenderer"
    )

SPECTACULAR_SETTINGS = {
    "TITLE": f"{PROJECT_NAME} API",
    "DESCRIPTION": PROJECT_DESCRIPTION,
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --------------------------------------------------------------------------
# Static files, i18n, logging
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {name} {message}", "style": "{"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
    },
}

# --------------------------------------------------------------------------
# Production hardening, applied whenever DEBUG is off.
# --------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    X_FRAME_OPTIONS = "DENY"
