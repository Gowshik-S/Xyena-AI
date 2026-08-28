FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY ledger_demo ./ledger_demo
COPY frontend ./frontend
RUN pip install --no-cache-dir .
EXPOSE 8095
CMD ["ledger-payment-demo"]
