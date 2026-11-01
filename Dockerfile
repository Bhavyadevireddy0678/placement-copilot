FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY ask_api.py api_security.py caches.py db_config.py retrieval.py resilience.py sql_generation.py sql_security.py ./
COPY static/ ./static/

EXPOSE 8000

CMD ["uvicorn", "ask_api:app", "--host", "0.0.0.0", "--port", "8000"]
