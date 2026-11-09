FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY retrieval/ ./retrieval/
COPY data/ ./data/
COPY dashboard/ ./dashboard/
COPY docs/schema.json ./docs/schema.json

# Generate the synthetic corpus and train the injection classifier inside the image.
RUN python data/generate.py && python app/guards/train_injection.py

RUN useradd --create-home appuser \
    && mkdir -p /data /app/data/cache \
    && chown -R appuser /app /data
USER appuser

EXPOSE 8000

HEALTHCHECK CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:%s/health' % __import__('os').environ.get('PORT','8000'))"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
