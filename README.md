# COP Forge

Modular Information Fusion System for Building Common Operational Pictures

## Description

CopForge is a modular, protocol-driven system designed to ingest heterogeneous sensor data and fuse it into a unified Common Operational Picture (COP). Built for interoperability and scalability, it leverages modern agent communication standards to create a flexible, framework-agnostic architecture. Note that the COP we are using is a toy-model one.

It is an evolution of the original [TIFDA](https://github.com/MartinezAgullo/genai-tifda) project.

<!-- Agentic mesh for the TIFDA (Tactical Information Fusion and Dissemination Agent) project -->

### What it does

1. **Multi-source Ingestion**: Accepts data from diverse sensors (radar, drones, manual reports, radio intercepts, etc) in various formats
2. **Intelligent Parsing**: Automatically detects formats and extracts entities, with LLM-powered multimodal processing for images, audio, and documents
3. **Entity Normalization**: Converts all inputs into a standardized EntityCOP format
4. **Sensor Fusion**: Merges observations from multiple sensors, deduplicates entities, and boosts confidence through multi-source confirmation
5. **COP Management**: Maintains and updates the operational picture with full audit trail

### Architecture

CopForge uses a decoupled architecture based on two protocols:

- **A2A Protocol** (Agent-to-Agent): For communication between intelligent agents that require reasoning or orchestration
- **MCP** (Model Context Protocol): For exposing deterministic tools that agents can invoke

### Project scaffolding

```bash
copforge/
├── pyproject.toml
├── src
│   ├── agents
│   ├── core
│   │   ├── config.py
│   │   ├── constants.py
│   │   └── telemetry.py
│   ├── mcp_servers
│   ├── models
│   │   ├── REAMDE.md
│   │   ├── cop.py
│   │   └── sensor.py
│   └── utils
└── tests
```

## Installation

```bash
# Clone and setup
git clone https://github.com/MartinezAgullo/copforge.git
cd copforge

# Create virtual environment (using UV recommended)
uv venv && source .venv/bin/activate

# Install pre-commit hooks
pre-commit install
pre-commit install --hook-type commit-msg
```

## Telemetry

CopForge implements a dual-stack observability strategy:

| System | Purpose | Use Cases |
| --- | --- | --- |
| **LangSmith** | LLM tracing | Prompt debugging, token usage, chain visualization |
| **OpenTelemetry** | Infrastructure tracing | A2A calls, MCP tool invocations, network latency |

LangSmith captures LLM-specific traces (prompts, completions, token counts), while OpenTelemetry handles everything else (HTTP requests, database queries, inter-service communication). Both can be correlated for end-to-end visibility. The outputs of Langsmith can be converted to OTel format.

**Configuration** (in `.env`):

```bash
# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-key
LANGCHAIN_PROJECT=copforge

# OpenTelemetry
TELEMETRY_OTEL_ENABLED=true
TELEMETRY_OTEL_EXPORTER_TYPE=otlp          # or "console" for local dev
TELEMETRY_OTEL_EXPORTER_ENDPOINT=http://localhost:4317  # Jaeger/Grafana
```

For local development, use `TELEMETRY_OTEL_EXPORTER_TYPE=console` to print traces to stdout, or run a local Jaeger instance.

## License

LGPL-3.0-or-later
<!--
tree -I "__pycache__|__init__.py|uv.lock|README.md"
-->
