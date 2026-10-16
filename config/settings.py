"""
Settings for the white-label spa platform.

Everything environment-specific is read from environment variables so the same
code runs in development and production. See .env.example.
"""
import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)

# The platform's own domain. Every business gets <slug>.<PLATFORM_DOMAIN>;
# the bare domain serves the platform landing page and the owner admin.
# In development "localhost" works because browsers send amani.localhost to 127.0.0.1.
PLATFORM_DOMAIN = os.environ.get("PLATFORM_DOMAIN", "localhost").lower()
PLATFORM_NAME = os.environ.get("PLATFORM_NAME", "Tenda")

# Custom domains are added at runtime, so they can't be listed here.
# TenantMiddleware returns 404 for any host that isn't the platform domain or a
# known tenant domain, which is what makes a wildcard safe behind a proxy.
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "*")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.accounts",
    "apps.tenants",
    "apps.spa",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.tenants.middleware.TenantMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
# Tenant hosts use their own URL map (booking site + business dashboard).
TENANT_URLCONF = "config.tenant_urls"

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
                "apps.tenants.context_processors.tenant",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


def database_from_url(url):
    """Parse postgres://user:pass@host:port/name without an extra dependency."""
    parsed = urlparse(url)
    if parsed.scheme in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
            "CONN_MAX_AGE": 60,
        }
    if parsed.scheme == "sqlite":
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": parsed.path or BASE_DIR / "db.sqlite3"}
    raise ValueError(f"Unsupported DATABASE_URL scheme: {parsed.scheme}")


DATABASES = {
    "default": database_from_url(os.environ["DATABASE_URL"])
    if os.environ.get("DATABASE_URL")
    else {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sessions are host-scoped by default, so a login on one business's domain
# never carries over to another business.
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", not DEBUG)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE

# Booking defaults
DEFAULT_DEPOSIT_PERCENT = 30
TRIAL_DAYS = 14

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
