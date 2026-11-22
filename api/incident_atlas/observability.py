from fastapi import FastAPI

from incident_atlas.config import Settings

_configured = False


def configure_otel(app: FastAPI, settings: Settings) -> None:
    global _configured
    if _configured:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return

    current = trace.get_tracer_provider()
    if current.__class__.__name__ == "ProxyTracerProvider":
        provider = TracerProvider(resource=Resource.create({"service.name": "incident-atlas-api"}))
        endpoint = settings.otel_exporter_otlp_endpoint
        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
            except ImportError:
                pass
        trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    _configured = True
