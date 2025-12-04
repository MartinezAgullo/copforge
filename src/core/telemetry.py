"""
Telemetry setup for CopForge.

Configures both LangSmith (for LLM tracing) and OpenTelemetry (for infrastructure).

Usage:
    from src.core.telemetry import setup_telemetry, get_tracer, traced_operation

    # Initialize at application startup
    telemetry_components = setup_telemetry()

    # Get a tracer for a component
    tracer = get_tracer("copforge.mcp.firewall")

    # Trace an operation
    with traced_operation(tracer, "validate_input", {"sensor_id": "radar_01"}) as span:
        result = validate(data)
        span.set_attribute("result.valid", result.is_valid)
"""

import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import wraps
from typing import Any, TypeVar

import structlog

from src.core.config import get_settings

logger = structlog.get_logger(__name__)

# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# LangSmith Setup (LLM Tracing)
# =============================================================================


def setup_langsmith() -> bool:
    """
    Configure LangSmith for LLM tracing.

    Sets environment variables that LangChain/LangGraph will pick up automatically.

    Returns:
        True if LangSmith was configured, False if disabled.
    """
    settings = get_settings()
    telemetry = settings.telemetry

    if not telemetry.langsmith_enabled:
        logger.info("LangSmith tracing disabled")
        return False

    # Set environment variables for LangChain
    os.environ["LANGCHAIN_TRACING_V2"] = str(telemetry.langsmith_tracing).lower()
    os.environ["LANGCHAIN_PROJECT"] = telemetry.langsmith_project

    if telemetry.langsmith_api_key:
        os.environ["LANGCHAIN_API_KEY"] = telemetry.langsmith_api_key.get_secret_value()
        logger.info(
            "LangSmith configured",
            project=telemetry.langsmith_project,
            tracing_enabled=telemetry.langsmith_tracing,
        )
        return True
    else:
        logger.warning(
            "LangSmith enabled but LANGCHAIN_API_KEY not set",
            project=telemetry.langsmith_project,
        )
        return False


# =============================================================================
# OpenTelemetry Setup (Infrastructure Tracing)
# =============================================================================

# Lazy imports to avoid loading OTel if not needed
_tracer_provider = None
_otel_initialized = False


def setup_opentelemetry() -> Any | None:
    """
    Configure OpenTelemetry for infrastructure tracing.

    Returns:
        TracerProvider instance or None if disabled.
    """
    global _tracer_provider, _otel_initialized

    if _otel_initialized:
        return _tracer_provider

    settings = get_settings()
    telemetry = settings.telemetry

    if not telemetry.otel_enabled:
        logger.info("OpenTelemetry tracing disabled")
        _otel_initialized = True
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        # Create resource with service name
        resource = Resource(attributes={SERVICE_NAME: telemetry.otel_service_name})

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Configure exporter based on settings
        if telemetry.otel_exporter_type == "otlp":
            exporter = OTLPSpanExporter(
                endpoint=telemetry.otel_exporter_endpoint,
                insecure=not telemetry.otel_exporter_endpoint.startswith("https"),
            )
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(
                "OpenTelemetry OTLP exporter configured",
                endpoint=telemetry.otel_exporter_endpoint,
            )
        elif telemetry.otel_exporter_type == "console":
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
            logger.info("OpenTelemetry console exporter configured")
        else:
            logger.info("OpenTelemetry exporter set to 'none', no spans will be exported")

        # Set as global tracer provider
        trace.set_tracer_provider(provider)

        logger.info(
            "OpenTelemetry configured",
            service_name=telemetry.otel_service_name,
            exporter=telemetry.otel_exporter_type,
        )

        _tracer_provider = provider
        _otel_initialized = True
        return provider

    except ImportError as e:
        logger.warning(
            "OpenTelemetry dependencies not installed, tracing disabled",
            error=str(e),
        )
        _otel_initialized = True
        return None


# =============================================================================
# Main Setup Function
# =============================================================================


def setup_telemetry() -> dict[str, Any]:
    """
    Initialize all telemetry systems.

    Call this once at application startup.

    Returns:
        Dictionary with telemetry components for reference/cleanup.

    Example:
        # In main.py or app startup
        from src.core.telemetry import setup_telemetry

        components = setup_telemetry()
        # ... run application ...
        # components["otel_provider"].shutdown() on exit
    """
    logger.info("Setting up telemetry...")

    # Configure LangSmith
    langsmith_ok = setup_langsmith()

    # Configure OpenTelemetry
    otel_provider = setup_opentelemetry()

    logger.info(
        "Telemetry setup complete",
        langsmith_enabled=langsmith_ok,
        otel_enabled=otel_provider is not None,
    )

    return {
        "langsmith_enabled": langsmith_ok,
        "otel_provider": otel_provider,
    }


# =============================================================================
# Tracer Utilities
# =============================================================================


def get_tracer(name: str) -> Any:
    """
    Get an OpenTelemetry tracer for the given component.

    If OpenTelemetry is not configured, returns a no-op tracer.

    Args:
        name: Name of the component (e.g., "copforge.mcp.firewall")

    Returns:
        Tracer instance (or NoOpTracer if OTel disabled).
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        # Return a no-op tracer if OTel not installed
        return _NoOpTracer()


@contextmanager
def traced_operation(
    tracer: Any,
    operation_name: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """
    Context manager for tracing an operation.

    Works with both real OTel tracers and the no-op tracer.

    Args:
        tracer: Tracer instance from get_tracer().
        operation_name: Name of the operation.
        attributes: Optional attributes to add to the span.

    Yields:
        The active span (or a no-op span).

    Example:
        tracer = get_tracer("copforge.mcp.firewall")
        with traced_operation(tracer, "validate_input", {"sensor_id": "radar_01"}) as span:
            result = validate(input_data)
            span.set_attribute("result.valid", result.is_valid)
    """
    if isinstance(tracer, _NoOpTracer):
        yield _NoOpSpan()
        return

    with tracer.start_as_current_span(operation_name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span

    # The @contextmanager decorator simplify the creating of context managers.
    # It allows you to write a generator function instead of defining a class with __enter__ and __exit__ methods.


def trace_function(
    tracer_name: str,
    operation_name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """
    Decorator to trace a function.

    Args:
        tracer_name: Name for the tracer (e.g., "copforge.mcp.firewall")
        operation_name: Name for the span (defaults to function name)
        attributes: Static attributes to add to every span

    Returns:
        Decorated function.

    Example:
        @trace_function("copforge.mcp.firewall")
        def validate_input(data: dict) -> bool:
            # ... validation logic ...
            return True
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer(tracer_name)
            span_name = operation_name or func.__name__
            with traced_operation(tracer, span_name, attributes):
                return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


# =============================================================================
# No-Op Classes (for when OTel is not installed)
# =============================================================================


class _NoOpSpan:
    """No-op span for when OpenTelemetry is not available."""

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op."""
        pass

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """No-op."""
        pass

    def set_status(self, status: Any) -> None:
        """No-op."""
        pass

    def record_exception(self, exception: Exception) -> None:
        """No-op."""
        pass


class _NoOpTracer:
    """No-op tracer for when OpenTelemetry is not available."""

    @contextmanager
    def start_as_current_span(self, _: str) -> Generator[_NoOpSpan, None, None]:
        """Return a no-op span."""
        yield _NoOpSpan()
