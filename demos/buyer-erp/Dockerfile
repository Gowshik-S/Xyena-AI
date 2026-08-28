FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system buyererp && adduser --system --ingroup buyererp buyererp

COPY pyproject.toml README.md ./
COPY erp_demo ./erp_demo
COPY frontend ./frontend
RUN pip install --no-cache-dir .

RUN chown -R buyererp:buyererp /app
USER buyererp

EXPOSE 8092

CMD ["buyer-erp-demo"]

