from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from packages.config import get_settings
from packages.persistence import get_database

_shared_configured = False


def configure_telemetry(app: FastAPI, service_name: str) -> None:
    _configure_shared(service_name)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health/live,health/ready",
    )


def configure_worker_telemetry(service_name: str) -> None:
    _configure_shared(service_name)


def _configure_shared(service_name: str) -> None:
    global _shared_configured
    settings = get_settings()
    if not _shared_configured:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.namespace": settings.otel_service_namespace,
                    "deployment.environment": settings.env,
                }
            )
        )
        if settings.otel_exporter_otlp_endpoint:
            provider.add_span_processor(
                BatchSpanProcessor(
                    OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
                )
            )
        trace.set_tracer_provider(provider)
        HTTPXClientInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument(engine=get_database().engine.sync_engine)
        _shared_configured = True
