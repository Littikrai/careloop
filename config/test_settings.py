import os
os.environ["DJANGO_SECRET_KEY"] = "test-only-not-for-deployment-" * 3
from .settings import *  # noqa: F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ALLOWED_HOSTS = ["testserver", "localhost"]
