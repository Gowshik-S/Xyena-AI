FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system funder && adduser --system --ingroup funder funder

COPY pyproject.toml README.md ./
COPY funder_demo ./funder_demo
COPY frontend ./frontend
RUN pip install --no-cache-dir .

RUN chown -R funder:funder /app
USER funder

EXPOSE 8093

CMD ["funder-marketplace-demo"]

