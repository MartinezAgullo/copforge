# CopForge Data Models

This folder contains all Pydantic data models for the CopForge system. These models define the data structures used throughout the application for sensor input processing, entity normalization, and operational picture management.

## Files

### `cop.py` - Common Operational Picture Models

Core models for the normalized operational picture. These represent entities **after** they have been processed and normalized from raw sensor data.

**Models:**

| Model | Description |
|-------|-------------|
| `Location` | Geographic coordinates (lat, lon, alt) with validation and 6-decimal precision |
| `EntityCOP` | Universal normalized entity - the core data structure for any tracked object (aircraft, vehicles, ships, personnel, infrastructure, events) |
| `ThreatAssessment` | Threat evaluation for entities, including threat level, affected assets, and reasoning |
| `COPSnapshot` | Point-in-time snapshot of the entire COP for checkpointing and audit |

**Type Aliases:**

| Type | Values |
|------|--------|
| `ClassificationType` | `friendly`, `hostile`, `neutral`, `unknown` (IFF) |
| `InfoClassificationLevel` | `UNCLASSIFIED`, `RESTRICTED`, `CONFIDENTIAL`, `SECRET`, `TOP_SECRET` |
| `EntityType` | `aircraft`, `fighter`, `bomber`, `helicopter`, `uav`, `missile`, `ground_vehicle`, `tank`, `apc`, `artillery`, `infantry`, `ship`, `destroyer`, `submarine`, `base`, `building`, `infrastructure`, `person`, `event`, `unknown` |
| `AccessLevel` | `top_secret_access`, `secret_access`, `confidential_access`, `restricted_access`, `unclassified_access`, `enemy_access` |

---

### `sensor.py` - Sensor Input Models

Models for raw sensor messages **before** normalization. Each sensor type (radar, drone, radio, etc.) sends data in different formats, but all share the common `SensorMessage` envelope.

**Core Models:**

| Model | Description |
|-------|-------------|
| `SensorMessage` | Universal input envelope for all sensor types. Contains sensor ID, type, timestamp, data payload, and optional file references |
| `SensorMessageBatch` | Collection of `SensorMessage` for bulk processing |
| `FileReference` | Reference to external files (audio, image, document, video) for multimodal processing |

**Format-Specific Models:**

These models define the structure of the `data` field within `SensorMessage` for each sensor type:

| Model | Sensor Type | Description |
|-------|-------------|-------------|
| `ASTERIXMessage` | `radar` | ASTERIX radar format with system ID and track list |
| `ASTERIXTrack` | `radar` | Individual radar track with position, speed, heading |
| `TrackQuality` | `radar` | Quality metrics (accuracy, plot count, SSR code) |
| `DroneData` | `drone` | UAV telemetry (position, altitude, battery, camera, image link) |
| `RadioData` | `radio` | Radio intercept metadata (frequency, modulation, audio path) |
| `ManualReport` | `manual` | Human-generated reports (SITREP, SPOTREP, SALUTE, etc.) |

**Type Aliases:**

| Type | Values |
|------|--------|
| `SensorType` | `radar`, `drone`, `manual`, `radio`, `ais`, `ads-b`, `link16`, `acoustic`, `sigint`, `imint`, `other` |
| `FileType` | `audio`, `image`, `document`, `video`, `unknown` |

---

## Usage Examples

### Creating a Sensor Message

```python
from datetime import datetime, timezone
from src.models import SensorMessage

# Radar message with ASTERIX data
radar_msg = SensorMessage(
    sensor_id="radar_01",
    sensor_type="radar",
    timestamp=datetime.now(timezone.utc),
    data={
        "format": "asterix",
        "system_id": "ES_RAD_101",
        "tracks": [
            {
                "track_id": "T001",
                "location": {"lat": 39.5, "lon": -0.4},
                "altitude_m": 5000,
                "speed_kmh": 450,
                "heading": 270,
            }
        ]
    }
)

# Check for file references (multimodal)
if radar_msg.has_file_references():
    files = radar_msg.get_file_references()
    # Process files...
```

### Creating a Normalized Entity

```python
from datetime import datetime, timezone
from src.models import EntityCOP, Location

entity = EntityCOP(
    entity_id="radar_01_T001",
    entity_type="aircraft",
    location=Location(lat=39.5, lon=-0.4, alt=5000),
    timestamp=datetime.now(timezone.utc),
    classification="unknown",
    information_classification="SECRET",
    confidence=0.9,
    source_sensors=["radar_01"],
    speed_kmh=450,
    heading=270,
    metadata={"track_id": "T001", "ssr_code": "7700"},
    comments="High-speed unknown aircraft"
)

# Get priority (higher for hostile/unknown)
priority = entity.get_priority()  # Returns 6 for "unknown"

# JSON-safe export (handles datetime)
json_data = entity.model_dump_json_safe()
```

### Drone with Image Reference

```python
from src.models import SensorMessage

drone_msg = SensorMessage(
    sensor_id="drone_alpha",
    sensor_type="drone",
    data={
        "drone_id": "DRONE_ALPHA_01",
        "latitude": 39.4762,
        "longitude": -0.3747,
        "altitude_m_agl": 120,
        "flight_mode": "auto",
        "battery_percent": 78,
        "image_link": "data/drone_alpha/IMG_001.jpg"
    }
)

# This will return True because of image_link
has_files = drone_msg.has_file_references()

# Get file references
files = drone_msg.get_file_references()
# {'image': 'data/drone_alpha/IMG_001.jpg'}
```

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SENSOR INPUTS                              │
│  SensorMessage (radar, drone, radio, manual, ais, ads-b, link16)    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FIREWALL VALIDATION                            │
│    - Prompt injection detection                                     │
│    - Coordinate validation                                          │
│    - Sensor authorization                                           │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PARSING & NORMALIZATION                          │
│    - Format-specific parsing (ASTERIX, Drone, Radio, Manual)        │
│    - Multimodal processing (audio, image, document)                 │
│    - Conversion to EntityCOP                                        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     COMMON OPERATIONAL PICTURE                      │
│    EntityCOP objects → Fusion → ThreatAssessment → COPSnapshot      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Related Modules

- `src/core/constants.py` - Validation constants and helper functions
- `src/core/config.py` - Application configuration
- `src/mcp_servers/firewall/` - Input validation MCP server
- `src/agents/ingest/` - Ingest agent using these models
