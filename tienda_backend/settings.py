"""
Django settings for tienda_backend project.
Corregido para Tienda Mixta Doña Jose - Juan Diego Contreras
"""

import os
from pathlib import Path
import environ

# 1. Inicializar environ
env = environ.Env()

# 2. Definir BASE_DIR
BASE_DIR = Path(__file__).resolve().parent.parent

# 3. Forzar la lectura del archivo .env usando la ruta absoluta
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))


# --- SEGURIDAD Y ENTORNO ---
# Ahora estas variables vienen de tu .env corregido
SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG', default=False)

ALLOWED_HOSTS = ['proyecto-tiendamovil.onrender.com', 'localhost', '127.0.0.1']

# --- CONFIGURACIÓN DE CORS Y CSRF ---
# Se pueden pasar como variables de entorno (coma-separadas) en Render.
# Ejemplo en Render: CORS_ALLOWED_ORIGINS=https://mi-frontend.onrender.com,https://otro
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=['http://localhost:3000'])

CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=['http://localhost:3000', 'http://127.0.0.1:3000'])
# 2. AGREGAR ESTO: Permite cualquier dominio dinámico que termine en .vercel.app
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://.*\.vercel\.app$", ]


CORS_ALLOW_CREDENTIALS = env.bool('CORS_ALLOW_CREDENTIALS', default=True)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "None"
SESSION_COOKIE_SECURE = True

# --- APPS INSTALADAS ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    
    # Apps de Terceros
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework.authtoken',
    'corsheaders',
    'drf_yasg',
    'dj_rest_auth',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'dj_rest_auth.registration',
    
    # App Local (SICEF)
    'core.apps.CoreConfig',
]

SITE_ID = 2

# --- BASE DE DATOS ---
# Selección de motor de base de datos basada en la variable de entorno USE_NEON.
# Por seguridad, las credenciales siguen en el archivo .env. Si USE_NEON es True,
# se intentará conectar a PostgreSQL (Neon) usando las variables DATABASE_*
USE_NEON = env.bool('USE_NEON', default=True)

if USE_NEON:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env('DATABASE_NAME'),
            'USER': env('DATABASE_USER'),
            'PASSWORD': env('DATABASE_PASS'),
            'HOST': env('DATABASE_HOST'),
            'PORT': env('DATABASE_PORT', default='5432'),
            'OPTIONS': {
                'sslmode': env('DATABASE_SSLMODE', default='require'),
                'channel_binding': env('DATABASE_CHANNEL_BINDING', default='require'),
            },
        }
    }
else:
    # Fallback a SQLite para desarrollo local
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# --- REST FRAMEWORK CONFIG ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

# --- CONFIGURACIÓN DE EMAIL ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'juandigarcia305@gmail.com'
# Lo ideal es que esta contraseña también vaya al .env
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='ojsb wkba dhkk aplh')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# --- MIDDLEWARE ---
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'tienda_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'tienda_backend.wsgi.application'

# --- VALIDACIÓN DE CONTRASEÑAS ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- INTERNACIONALIZACIÓN ---
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'core.Usuario'

REST_AUTH_REGISTER_SERIALIZERS = {
    'REGISTER_SERIALIZER': 'core.serializers.VendedorRegisterSerializer',
}