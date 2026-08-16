"""
Django settings for the JML access request tracker.

One codebase, many environments: nothing environment-specific is hardcoded here.
Every value that differs between a laptop, the Ubuntu box and a managed host is
read from the environment, so moving between them is a config change and never
a code change.
"""

from pathlib import Path

import environ

# BASE_DIR is the repo root (this file is jmltracker/jmltracker/settings.py).
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()

# Read .env if present. It is absent in production, where the process manager
# supplies real environment variables instead — hence no error when missing.
environ.Env.read_env(BASE_DIR / ".env")


# --- Core -------------------------------------------------------------------

# No default: an unset SECRET_KEY must stop the process, not quietly boot with a
# known-insecure value that could reach production.
SECRET_KEY = env.str("SECRET_KEY")

# Defaults to False so that forgetting the variable fails safe, never open.
DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

# Needed once the app is behind TLS on a real hostname; harmless when empty.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])


# --- Applications -----------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tracker",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise sits immediately after SecurityMiddleware so it can serve
    # static files without a separate web server in front of the app.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "jmltracker.urls"

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

WSGI_APPLICATION = "jmltracker.wsgi.application"


# --- Database ---------------------------------------------------------------

# DATABASE_URL is the single lever for database config in every environment.
# env.db() has no default on purpose: if DATABASE_URL is unset, Django raises
# ImproperlyConfigured and refuses to start. That is deliberate — a silent
# fallback to SQLite would let the app run locally on an engine it will never
# use in production, which is exactly how engine-specific bugs stay hidden
# until deployment. PostgreSQL is the only supported engine, everywhere.
DATABASES = {
    "default": env.db(),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Authentication ---------------------------------------------------------

# Every application view is behind @login_required; the login page and static
# files are the only anonymous routes.
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Internationalisation ---------------------------------------------------

LANGUAGE_CODE = "en-gb"

# Stored timestamps are UTC; TIME_ZONE only affects display. Env-driven so a
# deployment can render local time without a code change.
TIME_ZONE = env.str("TIME_ZONE", default="UTC")

USE_I18N = True
USE_TZ = True


# --- Static files -----------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Compresses and fingerprints static files at collectstatic time so they
        # can be cached hard by the browser.
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# --- Demo mode --------------------------------------------------------------

# Flags the public portfolio deployment (seeded, resettable, shared logins).
DEMO_MODE = env.bool("DEMO_MODE", default=False)

# Shared password for the two demo accounts, applied by the seed command. Read
# from the environment rather than hardcoded: it is a published credential, but
# publishing it in the README is a deliberate act, whereas baking it into a
# tracked .py file would put a working password in the repo by default. Empty
# (the default) means the demo accounts get unusable passwords and cannot be
# logged into at all — a fresh clone is inert until someone opts in.
DEMO_PASSWORD = env.str("DEMO_PASSWORD", default="")


# --- Security -------------------------------------------------------------

# Only meaningful behind TLS, so they are switched on by environment rather
# than hardcoded — on the laptop there is no HTTPS to redirect to.
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)

# HSTS is set by the application rather than the proxy so it travels with the
# code to hosts that have no Nginx in front. Defaults to 0 (off): a browser
# honours the max-age long after you stop serving TLS, so this is switched on
# per-environment, only once the certificate is known good.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

# Tells Django it is behind a reverse proxy terminating TLS (Nginx on the
# Ubuntu box), so request.is_secure() reports the truth.
if env.bool("USE_X_FORWARDED_PROTO", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
