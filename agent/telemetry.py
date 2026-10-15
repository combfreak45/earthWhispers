"""
OpenTelemetry tracing setup for EarthWhisper.

Provides a single `get_tracer()` used by the agent tools to emit spans
(`agent/tools/vertex_predictor.py`, `agent/tools/bq_mcp_client.py`, ...).

Behaviour:
- Initializes a real SDK TracerProvider once (idempotent), so spans carry real
  trace/span IDs — needed for the `trace_id` written to `earthwhisper_live.alert_audits`.
- Console span export is opt-in via `EARTHWHISPER_TRACE_CONSOLE=1` (handy for local runs).
- Google Cloud Trace export is opt-in via `EARTHWHISPER_TRACE_CLOUD=1`, and only if
  `opentelemetry-exporter-gcp-trace` is installed; otherwise it is silently skipped.
- If the OpenTelemetry SDK is unavailable for any reason, callers still get a valid
  no-op tracer from the API, so tool code never crashes on import.
"""

import os
import logging

from opentelemetry import trace

logger = logging.getLogger("earthwhisper-telemetry")

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "earthwhisper-agent")

_initialized = False


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _init_tracing() -> None:
    """Configure the global TracerProvider exactly once. Best-effort."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except Exception as e:  # SDK not installed — fall back to API no-op tracer
        logger.debug("OpenTelemetry SDK unavailable, using no-op tracer: %s", e)
        return

    # Don't clobber a provider someone else (e.g. ADK) already installed.
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        logger.debug("TracerProvider already configured; reusing it.")
        return

    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))

    if _truthy(os.getenv("EARTHWHISPER_TRACE_CONSOLE", "")):
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    if _truthy(os.getenv("EARTHWHISPER_TRACE_CLOUD", "")):
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            project_id = os.getenv("PROJECT_ID")
            exporter = CloudTraceSpanExporter(project_id=project_id) if project_id else CloudTraceSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("Cloud Trace exporter enabled.")
        except Exception as e:
            logger.warning("Cloud Trace export requested but unavailable: %s", e)

    trace.set_tracer_provider(provider)


def get_tracer(name: str = "earthwhisper"):
    """Return an OpenTelemetry tracer, initializing tracing on first use."""
    _init_tracing()
    return trace.get_tracer(name)


def get_current_trace_id() -> str:
    """
    Return the current span's trace ID as a 32-char hex string, or "" if there is
    no active/valid span. Used to stamp `alert_audits.trace_id`.
    """
    span = trace.get_current_span()
    ctx = span.get_span_context() if span else None
    if ctx and ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return ""
