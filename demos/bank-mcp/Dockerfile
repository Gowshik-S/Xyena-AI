FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system bankdemo && adduser --system --ingroup bankdemo bankdemo

COPY pyproject.toml README.md ./
COPY bank_demo ./bank_demo
COPY frontend ./frontend
RUN pip install --no-cache-dir .

RUN mkdir -p /data && chown -R bankdemo:bankdemo /app /data
USER bankdemo

EXPOSE 8090

CMD ["bank-mcp-demo"]
