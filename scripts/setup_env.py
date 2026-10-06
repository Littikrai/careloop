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
    config.write("OPENROUTER_API_KEY=\n")
    config.write("OPENROUTER_MODEL=openrouter/free\n")
    config.write("EMBEDDING_MODEL=intfloat/multilingual-e5-small\n")
    config.write("DOCUMENT_CHUNK_MAX_TOKENS=256\n")
    config.write("DOCUMENT_CHUNK_TARGET_TOKENS=224\n")
    config.write("DOCUMENT_MAX_CHUNKS=256\n")
    config.write("DOCUMENT_EMBED_BATCH_SIZE=16\n")
    config.write("DOCUMENT_INDEX_BUDGET_SECONDS=240\n")
    config.write("DOCUMENT_INDEX_LEASE_SECONDS=300\n")
    config.write("GUNICORN_THREADS=3\n")
    config.write("RAG_SCORE_THRESHOLD=0.55\n")
    config.write("RAG_TOP_K=3\n")
    config.write("CHAT_RATE_LIMIT_PER_MINUTE=30\n")
    config.write("API_RATE_LIMIT_PER_MINUTE=30\n")
    config.write("PUBLIC_BASE_URL=http://localhost:8080\n")
print("Created .env with a unique secret. No administrator password was created.")
