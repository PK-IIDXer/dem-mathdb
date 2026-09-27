FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY dem ./dem
COPY demlang ./demlang
COPY webapi ./webapi
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir ".[webapi,postgres]"

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn webapi.main:app --host 0.0.0.0 --port 8000"]
