"""
Django settings for vught_pace_keeper project.
"""

import os
from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Points to project root

# Initialize environ
env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

# Read .env file if it exists
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(env_file)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY", default="dev-secret-key-change-in-production")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",  # GeoDjango
    "django.contrib.sites",  # Required by allauth
    # Allauth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.strava",
    # HTMX
    "django_htmx",
    # Local apps
    "vught_pace_keeper.core",
    "vught_pace_keeper.accounts",
    "vught_pace_keeper.training",
    "vught_pace_keeper.strava_integration",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",  # Required by allauth
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "vught_pace_keeper.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "src" / "vught_pace_keeper" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "vught_pace_keeper.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases
# PostGIS via django-environ: postgis:// schema maps to django.contrib.gis.db.backends.postgis

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgis://vught_user:vught_secret_password@localhost:5432/vught_pace_keeper",
    ),
}


# Custom User Model
AUTH_USER_MODEL = "accounts.User"


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Europe/Amsterdam"  # Netherlands timezone for Vught

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = env("STATIC_ROOT", default=BASE_DIR / "staticfiles")

MEDIA_URL = "media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=BASE_DIR / "media")


# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# =============================================================================
# Django Allauth Configuration
# =============================================================================

SITE_ID = 1

# Authentication backends
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Email backend (console for development)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Allauth account settings (updated for django-allauth 65+)
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"  # Disable for easier local dev
ACCOUNT_UNIQUE_EMAIL = True
LOGIN_REDIRECT_URL = "/dashboard/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True

# Auto-link accounts by email
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

# Adapters
ACCOUNT_ADAPTER = "vught_pace_keeper.accounts.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "vught_pace_keeper.accounts.adapters.SocialAccountAdapter"

# Fernet encryption settings (for encrypted token storage)
# Uses SECRET_KEY as the encryption key by default
FERNET_KEY = env("FERNET_KEY", default=SECRET_KEY)
SALT_KEY = env("SALT_KEY", default=SECRET_KEY[:16])

# Strava provider configuration
STRAVA_CLIENT_ID = env("STRAVA_CLIENT_ID", default="")
STRAVA_CLIENT_SECRET = env("STRAVA_CLIENT_SECRET", default="")

SOCIALACCOUNT_PROVIDERS = {
    "strava": {
        "SCOPE": ["read,activity:read_all"],
        "VERIFIED_EMAIL": True,
    }
}

# Add Strava credentials to provider config if available
if STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET:
    SOCIALACCOUNT_PROVIDERS["strava"]["APPS"] = [
        {
            "client_id": STRAVA_CLIENT_ID,
            "secret": STRAVA_CLIENT_SECRET,
        }
    ]
