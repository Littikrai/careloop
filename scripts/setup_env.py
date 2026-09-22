"""Create local Compose configuration without overwriting an existing secret."""
import os
import secrets
from pathlib import Path

path = Path(__file__).resolve().parent.parent / ".env"
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit(".env already exists; keeping your current configuration.")
with os.fdopen(fd, "w") as config:
    config.write(f"DJANGO_SECRET_KEY={secrets.token_hex(48)}\n")
    config.write("DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1]\n")
    config.write("DJANGO_HTTPS_ONLY=false\n")
print("Created .env with a unique secret. No administrator password was created.")
