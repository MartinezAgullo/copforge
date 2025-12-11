# CopForge

Modular Information Fusion System for Building Common Operational Pictures.

## Overview

CopForge is a modular, protocol-driven system designed to ingest heterogeneous sensor data and fuse it into a unified Common Operational Picture (COP). Built for interoperability and scalability, it leverages modern agent communication standards.

It is an evolution of the [TIFDA](https://github.com/MartinezAgullo/genai-tifda) project.

## Architecture

CopForge uses a decoupled architecture based on two protocols:

- **A2A Protocol** (Agent-to-Agent): For communication between intelligent agents
- **MCP** (Model Context Protocol): For exposing deterministic tools that agents can invoke

```
┌─────────────────────────────────────────────────────────────────────┐
│                        INGEST AGENT                                 │
│  (A2A Server + LangGraph)                                           │
│                                                                     │
│  1. Receives SensorMessage                                          │
│  2. Applies Firewall (src/security/)                                │
│  3. Parses (src/parsers/)                                           │
│  4. Calls MCP Multimodal if files present                           │
│  5. Returns List[EntityCOP]                                         │
│                                                                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     MCP SERVER: COP FUSION                          │
│  (Deterministic, no LLM)                                            │
│                                                                     │
│  Tools:                                                             │
│  - normalize_entities(entities) → List[EntityCOP]                   │
│  - find_duplicates(entity, cop) → List[match]                       │
│  - merge_entities(entity1, entity2) → EntityCOP                     │
│  - update_cop(entities) → stats                                     │
│  - query_cop(filters) → List[EntityCOP]                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```bash
copforge/
├── pyproject.toml
├── src/
│   ├── agents/              # A2A Agents (Ingest Agent, etc.)
│   │   └── ingest/
│   ├── core/                # Configuration, constants, telemetry
│   │   ├── config.py
│   │   ├── constants.py
│   │   └── telemetry.py
│   ├── mcp_servers/         # MCP Servers
│   │   ├── cop_fusion/      # COP operations (merge, update, query)
│   │   └── multimodal/      # Audio, image, document processing
│   ├── models/              # Pydantic data models
│   │   ├── cop.py           # EntityCOP, Location, ThreatAssessment
│   │   └── sensor.py        # SensorMessage, format-specific models
│   ├── parsers/             # Sensor format parsers
│   │   ├── base_parser.py
│   │   ├── asterix_parser.py
│   │   ├── drone_parser.py
│   │   ├── radio_parser.py
│   │   ├── manual_parser.py
│   │   └── parser_factory.py
│   ├── security/            # Security validation
│   │   └── firewall.py
│   └── utils/
└── tests/
    ├── parsers/
    └── security/
```

## Implemented Features

### Security Firewall (`src/security/`)

Multi-layer security validation for incoming sensor data:

- Sensor authorization (whitelist-based)
- Message structure validation
- Prompt injection detection
- Coordinate validation
- Classification/access control

```python
from src.security import validate_sensor_input, validate_entity

# Validate incoming sensor message
result = validate_sensor_input(sensor_msg)
if not result.is_valid:
    print(f"Blocked: {result.error}")

# Validate entity before COP insertion
result = validate_entity(entity)
```

### Parsers (`src/parsers/`)

Format-specific parsers with Strategy pattern:

| Parser | Sensor Type | Description |
|--------|-------------|-------------|
| `ASTERIXParser` | radar | ASTERIX radar format (JSON) |
| `DroneParser` | drone | UAV telemetry and imagery |
| `RadioParser` | radio | Radio intercept metadata |
| `ManualParser` | manual | Human-generated reports (SITREP, SPOTREP) |

```python
from src.parsers import get_parser_factory

factory = get_parser_factory()
result = factory.parse(sensor_msg)

if result.success:
    for entity in result.entities:
        print(f"Created: {entity.entity_id}")
```

### Telemetry (`src/core/telemetry.py`)

Dual telemetry stack:

| System | Purpose |
|--------|---------|
| **LangSmith** | LLM call tracing (prompts, tokens, latency) |
| **OpenTelemetry** | Infrastructure tracing (HTTP, MCP tools, A2A) |

```python
from src.core.telemetry import setup_telemetry, get_tracer, traced_operation

# Initialize at startup
setup_telemetry()

# Trace operations
tracer = get_tracer("copforge.my_module")
with traced_operation(tracer, "my_operation", {"key": "value"}) as span:
    result = do_something()
    span.set_attribute("result", result)
```

## Installation

```bash
# Clone repository
git clone https://github.com/MartinezAgullo/copforge.git
cd copforge

# Create virtual environment
python -m venv .venv # or use: uv venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows



# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## Configuration

Configure .env:

```bash
# LangSmith (LLM Tracing)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-key
LANGCHAIN_PROJECT=copforge

# OpenTelemetry (Infrastructure Tracing)
TELEMETRY_OTEL_ENABLED=true
TELEMETRY_OTEL_EXPORTER_TYPE=otlp  # or "console" for local dev
TELEMETRY_OTEL_EXPORTER_ENDPOINT=http://localhost:4317

# LLM Providers
OPENAI_API_KEY=sk-your-key
ANTHROPIC_API_KEY=sk-ant-your-key
LLM_DEFAULT_PROVIDER=openai
```

## Roadmap

- [x] Security Firewall
- [x] Sensor Parsers (ASTERIX, Drone, Radio, Manual)
- [x] Telemetry (LangSmith + OpenTelemetry)
- [ ] Ingest Agent (A2A + LangGraph)
- [ ] COP Fusion MCP Server
- [ ] Multimodal MCP Server (audio, image, document)
- [ ] Threat Evaluator Agent
- [ ] Dissemination Agent

## License

LGPL-3.0-or-later
<!--
tree -I "__pycache__|__init__.py|uv.lock|README.md"
-->
