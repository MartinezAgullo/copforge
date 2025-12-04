# CopForge Core

This folder contains core infrastructure modules used throughout the CopForge system.

## Files

### `config.py` - Configuration Management

Uses Pydantic Settings for environment variable parsing with validation.

**Classes:**

| Class | Env Prefix | Description |
|-------|------------|-------------|
| `Settings` | - | Main application settings |
| `TelemetrySettings` | `TELEMETRY_` | LangSmith + OpenTelemetry config |
| `A2ASettings` | `A2A_` | A2A Protocol agent configuration |
| `MCPSettings` | `MCP_` | MCP server host/port configuration |
| `LLMSettings` | `LLM_` | OpenAI/Anthropic API keys and models |

**Usage:**

```python
from src.core.config import get_settings

settings = get_settings()

# Access nested settings
print(settings.telemetry.langsmith_project)  # "copforge"
print(settings.llm.openai_model)  # "gpt-4o"
print(settings.mcp.firewall_port)  # 8010
```

---

### `telemetry.py` - Observability Setup

Dual telemetry stack:
- **LangSmith**: LLM call tracing (prompts, tokens, latency)
- **OpenTelemetry**: Infrastructure tracing (HTTP calls, database, MCP tools)

**Functions:**

| Function | Description |
|----------|-------------|
| `setup_telemetry()` | Initialize all telemetry (call once at startup) |
| `setup_langsmith()` | Configure LangSmith environment variables |
| `setup_opentelemetry()` | Configure OTel TracerProvider and exporter |
| `get_tracer(name)` | Get a tracer for a component |
| `traced_operation(tracer, name, attrs)` | Context manager for tracing |
| `@trace_function(tracer_name)` | Decorator for function tracing |

**Usage:**

```python
# At application startup
from src.core.telemetry import setup_telemetry

components = setup_telemetry()

# In your code - context manager style
from src.core.telemetry import get_tracer, traced_operation

tracer = get_tracer("copforge.mcp.firewall")

def validate_input(data: dict) -> bool:
    with traced_operation(tracer, "validate_input", {"sensor_id": data.get("sensor_id")}) as span:
        result = _do_validation(data)
        span.set_attribute("result.valid", result)
        return result

# Or use the decorator
from src.core.telemetry import trace_function

@trace_function("copforge.mcp.firewall")
def validate_input(data: dict) -> bool:
    return _do_validation(data)
```

**No-Op Behavior:**
If OpenTelemetry dependencies are not installed, the module provides no-op implementations that silently do nothing. This allows code to use tracing unconditionally without import errors.

---

### `constants.py` - System Constants

Centralized definitions for validation and access control.

**Constants:**

| Constant | Type | Description |
|----------|------|-------------|
| `SENSOR_TYPES` | `set[str]` | Valid sensor types |
| `CLASSIFICATIONS` | `set[str]` | IFF classifications (friendly, hostile, etc.) |
| `CLASSIFICATION_LEVELS` | `list[str]` | Security levels (UNCLASSIFIED → TOP_SECRET) |
| `CLASSIFICATION_HIERARCHY` | `dict[str, int]` | Numeric hierarchy for comparison |
| `ACCESS_LEVELS` | `set[str]` | User access levels |
| `ENTITY_TYPES` | `set[str]` | Valid entity types |

**Functions:**

| Function | Description |
|----------|-------------|
| `can_access_classification(access, class)` | Check if access level can read classification |
| `get_classification_level(class)` | Get numeric level for comparison |
| `is_valid_sensor_type(type)` | Validate sensor type |
| `is_valid_classification(class)` | Validate IFF classification |
| `is_valid_info_classification(class)` | Validate security classification |
| `is_valid_access_level(level)` | Validate access level |
| `is_valid_entity_type(type)` | Validate entity type |

**Usage:**

```python
from src.core.constants import (
    SENSOR_TYPES,
    can_access_classification,
    is_valid_sensor_type,
)

# Check if sensor type is valid
if not is_valid_sensor_type("radar"):
    raise ValueError("Invalid sensor type")

# Check access control
if not can_access_classification("secret_access", "TOP_SECRET"):
    raise PermissionError("Access denied")
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# LangSmith (LLM Tracing)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_your-key
LANGCHAIN_PROJECT=copforge

# OpenTelemetry (Infrastructure Tracing)
TELEMETRY_OTEL_ENABLED=true
TELEMETRY_OTEL_SERVICE_NAME=copforge
TELEMETRY_OTEL_EXPORTER_TYPE=otlp  # or "console" or "none"
TELEMETRY_OTEL_EXPORTER_ENDPOINT=http://localhost:4317

# LLM Providers
OPENAI_API_KEY=sk-your-key
ANTHROPIC_API_KEY=sk-ant-your-key
LLM_DEFAULT_PROVIDER=openai
```

---

## Telemetry Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                         APPLICATION                                │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐            │
│   │   Ingest    │    │   Firewall  │    │ COP Fusion  │            │
│   │   Agent     │    │   MCP Tool  │    │  MCP Tool   │            │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘            │
│          │                  │                  │                   │
│          ▼                  ▼                  ▼                   │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │                    TELEMETRY LAYER                          │  │
│   │  ┌──────────────────┐    ┌──────────────────────────────┐   │  │
│   │  │    LangSmith     │    │       OpenTelemetry          │   │  │
│   │  │  (LLM Traces)    │    │   (Infrastructure Traces)    │   │  │
│   │  └────────┬─────────┘    └─────────────┬────────────────┘   │  │
│   └───────────┼─────────────────────────────┼───────────────────┘  │
└───────────────┼─────────────────────────────┼──────────────────────┘
                │                             │
                ▼                             ▼
        ┌───────────────┐           ┌──────────────────┐
        │ LangSmith API │           │  OTLP Collector  │
        │ (Cloud Only)  │           │ (Jaeger/Grafana) │
        └───────────────┘           └──────────────────┘
```

**What goes where:**

| Telemetry System | Use For |
|------------------|---------|
| LangSmith | LLM calls, prompt debugging, token usage, chain traces |
| OpenTelemetry | HTTP requests, database queries, MCP tool calls, A2A messages, network latency |

---

## Local Development

For local development without external telemetry services:

```bash
# Disable LangSmith
TELEMETRY_LANGSMITH_ENABLED=false

# Use console exporter for OTel (prints to stdout)
TELEMETRY_OTEL_EXPORTER_TYPE=console

# Or disable OTel entirely
TELEMETRY_OTEL_ENABLED=false
```

To run a local Jaeger instance for trace visualization:

```bash
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/all-in-one:latest
```

Then set:
```bash
TELEMETRY_OTEL_EXPORTER_ENDPOINT=http://localhost:4317
```

View traces at: http://localhost:16686