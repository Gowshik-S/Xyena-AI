FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --system --gid 10001 xyena \
    && useradd --system --uid 10001 --gid xyena --home-dir /app xyena

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
RUN pip install --upgrade pip \
    && pip install .

USER 10001:10001
EXPOSE 8080 8081 8082
CMD ["python", "-m", "apps.api.main"]
