FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system gstportal && adduser --system --ingroup gstportal gstportal

COPY pyproject.toml README.md ./
COPY gst_portal ./gst_portal
COPY frontend ./frontend
RUN pip install --no-cache-dir .

RUN chown -R gstportal:gstportal /app
USER gstportal

EXPOSE 8091

CMD ["gst-portal-demo"]
