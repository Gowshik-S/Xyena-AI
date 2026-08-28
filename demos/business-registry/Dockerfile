FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system registry && adduser --system --ingroup registry registry

COPY pyproject.toml README.md ./
COPY business_registry ./business_registry
COPY frontend ./frontend
RUN pip install --no-cache-dir .

RUN chown -R registry:registry /app
USER registry

EXPOSE 8093

CMD ["business-registry-demo"]
