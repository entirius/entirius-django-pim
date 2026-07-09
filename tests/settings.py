# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import os

import dj_database_url

# PATHS
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Django app folder
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "."))  # ROOT for STATIC_ROOT and MEDIA_ROOT
TMP_DIR = os.path.join(DATA_DIR, "tmp/pim-test/")  # Where to store temporary files
STATIC_ROOT = os.path.join(DATA_DIR, "static/pim-test/")  # Where to store static files
MEDIA_ROOT = os.path.join(DATA_DIR, "media/pim-test/")  # Where to store media files(images, pdf, etc.)

# URLS
STATIC_URL = "static/"
MEDIA_URL = "media/"

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "not so secret test secret"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True
LOG_TRACEBACK = True
INCLUDE_ERR_IN_RESPONSE = True

ALLOWED_HOSTS = ["*"]

# URLS
ADMIN_BASE_URL = "admin"
API_PUBLIC_BASE_URL = "api"
API_ADMIN_BASE_URL = "api-admin"


# Application definition
WSGI_APPLICATION = "main.wsgi.application"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "django_regional",
    "django_pim",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]


#
# Database configuration
#
# Postgres required (UniqueConstraint nulls_distinct); CI provides DATABASE_URL,
# locally point it at any postgres 15+ (default matches the CI service).
DATABASES = {
    "default": dj_database_url.config(default="postgresql://postgres:postgres@localhost:5432/test"),
}


#
# Auth backends
#
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]


# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = []


# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = "/static/"

#
# Django 3.2
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

#
# Business Intelligence settings
#
BI_ENVIRONMENT = "test-local"
BI_BUSINESS_UNIT = "test"

#
# Use test url conf
#
ROOT_URLCONF = "django_pim.urls"

#
# Translation settings
#
T9N_DEFAULT_LANG = "en"
