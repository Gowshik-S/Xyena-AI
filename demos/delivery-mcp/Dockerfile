FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system deliverydemo && adduser --system --ingroup deliverydemo deliverydemo

COPY pyproject.toml README.md ./
COPY delivery_demo ./delivery_demo
COPY frontend ./frontend
RUN pip install --no-cache-dir .

RUN mkdir -p /data && chown -R deliverydemo:deliverydemo /app /data
USER deliverydemo

EXPOSE 8095

CMD ["delivery-mcp-demo"]
