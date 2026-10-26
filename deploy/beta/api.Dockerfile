FROM python:3.13.7-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl --fail --silent --show-error https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home beta
COPY pyproject.toml README.md alembic.ini ./
COPY dem ./dem
COPY demlang ./demlang
COPY webapi ./webapi
COPY alembic ./alembic
COPY scripts/beta_admin.py scripts/beta_base.py ./scripts/
COPY deploy/beta/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir --no-deps -r requirements.lock \
    && pip install --no-cache-dir --no-deps .
USER 10001:10001
CMD ["uvicorn", "webapi.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--loop", "asyncio", "--proxy-headers", "--forwarded-allow-ips", "172.30.42.2", "--limit-concurrency", "32", "--timeout-keep-alive", "5"]
