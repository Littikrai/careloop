FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data HF_HOME=/data/huggingface TOKENIZERS_PARALLELISM=false
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch==2.14.0+cpu \
    && pip install --no-cache-dir -r requirements.txt
COPY manage.py ./
COPY config ./config
COPY businesses ./businesses
RUN DJANGO_SECRET_KEY=build-only-placeholder-not-a-runtime-secret-1234567890 python manage.py collectstatic --noinput \
    && mkdir -p /data && chown -R 10001:10001 /data
USER 10001:10001
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py recover_document_indexing --startup && python manage.py shell -c \"from businesses.vector_store import embed_document; embed_document('warmup')\" && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --worker-class gthread --workers 1 --threads \"${GUNICORN_THREADS:-3}\" --timeout 300 --no-control-socket --access-logfile - --error-logfile -"]
