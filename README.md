# CopForge

Modular Information Fusion System for Building Common Operational Pictures.

## Overview

CopForge is a modular, protocol-driven system designed to ingest heterogeneous sensor data and fuse it into a unified Common Operational Picture (COP).
<!-- Built for interoperability and scalability, it leverages modern agent communication standards. -->

It is an evolution of the [TIFDA](https://github.com/MartinezAgullo/genai-tifda) project.

## Architecture

CopForge uses (or intends to use) a decoupled architecture based on two protocols:

- **A2A Protocol** (Agent-to-Agent): For communication between intelligent agents. For future if an autonomous AI agent is implemented See discussion [AI Pipeline vs AI Agent](https://github.com/MartinezAgullo/copforge/blob/main/data/docs/agency_spectrum_copforge_V2.pdf).
<!-- (just maybe, because for DAG we won't use A2A but if we convert this into an actual autonomous AI agent, then A2A will be used). -->
    - CopForge features as of today (DAG):
        - Predefined control flow (LangGraph).
        - No self-formulated objectives: The LLM does not define its own goals.
        - Absence of:
            - Open-ended planning
            - Negotiation
            - Dynamic delegation
            - Unbounded perception–action cycles

- **MCP** (Model Context Protocol): For exposing deterministic tools that agents can invoke

![architecture](https://github.com/MartinezAgullo/copforge/blob/main/data/img/Esquema_CopForge_a.png)

<!--
```bash
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
│  - find_duplicates(entity, cop) → List[match]                       │
│  - merge_entities(entity1, entity2) → EntityCOP                     │
│  - update_cop(entities) → stats                                     │
│  - query_cop(filters) → List[EntityCOP]                             │
│  - get_cop_stats() → stats                                          │
│  - sync_to_mapa() / load_from_mapa() / check_mapa_connection()      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```
-->

## Project Structure

```bash
copforge/
├── pyproject.toml
├── src/
│   ├── main.py                     # ✅ NEW: E2E pipeline entry point
│   ├── mcp_client.py               # ✅ NEW: MCP client for COP Fusion server
│   ├── core/                       # Configuration, constants, telemetry
│   │   ├── config.py               # Pydantic Settings for environment config
│   │   ├── constants.py            # Sensor types, entity types, classifications
│   │   └── telemetry.py            # LangSmith + OpenTelemetry setup
│   ├── mcp_servers/                # MCP Servers (using official mcp SDK)
│   │   ├── cop_fusion/             # COP operations server
│   │   │   ├── server.py           # MCP server entry point with 8 tools
│   │   │   ├── state.py            # COPState: thread-safe in-memory store
│   │   │   ├── tools.py            # Tool implementations (find, merge, query...)
│   │   │   ├── cop_sync.py         # Bidirectional sync with mapa-puntos-interes
│   │   │   └── mapa_client.py      # HTTP client for mapa REST API
│   │   └── multimodal/             # Audio, image, document processing server
│   │       ├── server.py           # MCP server entry point with 3 tools
│   │       ├── audio_tools.py      # Whisper + Pyannote diarization
│   │       ├── image_tools.py      # VLM analysis (GPT-4o, Claude)
│   │       └── document_tools.py   # PDF, DOCX, TXT extraction
│   ├── models/                     # Pydantic data models
│   │   ├── cop.py                  # EntityCOP, Location, ThreatAssessment
│   │   └── sensor.py               # SensorMessage, format-specific models
│   ├── parsers/                    # Sensor format parsers (Strategy pattern)
│   │   ├── base_parser.py          # Abstract base class
│   │   ├── asterix_parser.py       # ASTERIX radar format (JSON)
│   │   ├── drone_parser.py         # UAV telemetry and imagery
│   │   ├── radio_parser.py         # Radio intercept metadata
│   │   ├── manual_parser.py        # Human reports (SITREP, SPOTREP)
│   │   └── parser_factory.py       # Factory for parser selection
│   ├── security/                   # Security validation
│   │   └── firewall.py             # Multi-layer input validation
│   ├── agents/                     # Future (optional): A2A Agents / LangGraph flows
│   │   └── ingest/                 # Placeholder for Ingest Agent
│   │       └── TODO?
│   └── utils/                      # Utility functions
└── tests/
    ├── mcp_servers/
    │   ├── test_cop_fusion.py      # 39 tests for COP fusion
    │   └── test_multimodal.py      # 36 tests for multimodal
    ├── parsers/
    │   └── test_parsers.py         # Parser unit tests
    ├── security/
    │   └── test_firewall.py        # Firewall unit tests
    │
    └── integration/                # Future: E2E integration tests
        └── TODO
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

### MCP Server: COP Fusion (`src/mcp_servers/cop_fusion/`)

Server for managing the Common Operational Picture. Built with the official MCP SDK (`from mcp.server import Server`).

**Features:**

- Thread-safe in-memory state (`COPState`)
- Haversine-based duplicate detection (spatial + temporal scoring)
- Bidirectional sync with [mapa-puntos-interes](https://github.com/MartinezAgullo/mapa-puntos-interes) REST API
- OpenTelemetry tracing on all operations

**Tools (8 total):**

| Tool | Description |
|------|-------------|
| `find_duplicates` | Find potential duplicates using Haversine distance + time window + classification |
| `merge_entities` | Merge two entities (uses newest timestamp location, combines sensors) |
| `update_cop` | Batch add/update entities with auto-sync to mapa |
| `query_cop` | Query entities with filters (type, classification, bbox, time, confidence) |
| `get_cop_stats` | Get COP statistics (entity counts, sync status) |
| `sync_to_mapa` | Manual push all entities to mapa-puntos-interes |
| `load_from_mapa` | Manual pull all entities from mapa-puntos-interes |
| `check_mapa_connection` | Health check for mapa REST API |

```bash
# Run standalone
uv run python -m src.mcp_servers.cop_fusion.server

# With MCP Inspector
npx @anthropic/mcp-inspector uv run python -m src.mcp_servers.cop_fusion.server
```

### MCP Server: Multimodal (`src/mcp_servers/multimodal/`)

Server for processing audio, images, and documents. Built with the official MCP SDK.

**Tools (3 total):**

| Tool | Description | Requirements |
|------|-------------|--------------|
| `transcribe_audio` | Speech-to-text with speaker diarization | Whisper, Pyannote, `HF_TOKEN` |
| `analyze_image` | VLM-based tactical image analysis | OpenAI/Anthropic API key |
| `process_document` | Text extraction from documents | PyPDF2, python-docx |

**Supported formats:**

- Audio: mp3, wav, m4a, flac, ogg, aac, wma
- Images: jpg, png, gif, bmp, webp, tiff
- Documents: pdf, txt, docx

**Image analysis types:**

- `general`: Full tactical assessment
- `asset_detection`: Military vehicles, aircraft, equipment
- `terrain`: Geographic and terrain analysis
- `damage`: Damage assessment
- `custom`: Custom prompt

```bash
# Run standalone
uv run python -m src.mcp_servers.multimodal.server

# With MCP Inspector
npx @anthropic/mcp-inspector uv run python -m src.mcp_servers.multimodal.server
```
* * * * *
## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/MartinezAgullo/copforge.git
cd copforge

# Create virtual environment
uv venv # or: python -m venv .venv
source .venv/bin/activate # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -e ".[dev]"  # or: pip install -e ".[dev]"

# Run tests
uv run pytest tests/ -v
```

### Configuration

Configure `.env`:

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

# Mapa Integration
MAPA_BASE_URL=http://localhost:3000

# Multimodal (for speaker diarization)
HF_TOKEN=hf-your-token
```

### Execution

#### Prerequisites
1. **Map visualization** - Download [mapa-puntos-interes](https://github.com/MartinezAgullo/mapa-puntos-interes)
2. **PostgreSQL** - Required for map backend (usually via Docker Compose in the map repo)
<!-- The first step is to run the interactive map for the COP. It can be downlodad from [here](https://github.com/MartinezAgullo/mapa-puntos-interes). -->

#### Complete Startup Sequence

```bash
# Terminal 1: Start PostgreSQL & map visualization
./start_cop_map.sh
```

```bash
# Terminal 2: Run the demo
uv run python -m src.main
```

```bash
# COP Fusion
uv run python -m src.mcp_servers.cop_fusion.server
```

```bash
# With MCP Inspector
npx @anthropic/mcp-inspector uv run python -m src.mcp_servers.cop_fusion.server
```

### Testing

```bash
# All tests
uv run pytest

# Specific tests
uv run pytest tests/security/test_firewall.py -v
uv run pytest tests/parsers/test_parsers.py -v
uv run pytest tests/mcp_servers/test_cop_fusion.py -v
uv run pytest tests/mcp_servers/test_multimodal.py -v

# With coverage
uv run pytest --cov=src --cov-report=term-missing
```

## Roadmap

- [x] Security Firewall
- [x] Sensor Parsers (ASTERIX, Drone, Radio, Manual)
- [x] Telemetry (LangSmith + OpenTelemetry)
- [x] COP Fusion MCP Server
- [x] Multimodal MCP Server (audio, image, document)
- [x] Bidirectional sync with mapa-puntos-interes
- [ ] Ingest Agent (A2A + LangGraph) OR Ingest AI Flux
- [ ] Orchestration system (multi-agent coordination) <- Don't know if necessary
- [ ] Enhanced duplicate detection (velocity, heading, type-specific thresholds) <- Already done in Mosaico project
- [ ] Transition from monorepo to multirepo or specialized packages

## License

LGPL-3.0-or-later

<!--
tree -I "__pycache__|__init__.py|uv.lock|README.md|agency_spectrum_copforge.pdf"
-->
