# MCP Server: COP Fusion

Deterministic MCP server for Common Operational Picture operations. Provides tools for duplicate detection, entity merging, COP updates, and queries.

---

## 🏗️ Architecture

```bash
Agent (LangGraph)
    │
    │ MCP Protocol (stdio/SSE)
    ▼
┌─────────────────────────────────────────────────┐
│           MCP SERVER: COP FUSION                │
│                                                 │
│  Tools:                                         │
│  ├─ find_duplicates()  → Haversine + time      │
│  ├─ merge_entities()   → Sensor fusion         │
│  ├─ update_cop()       → Add/update batch      │
│  ├─ query_cop()        → Filtered queries      │
│  └─ get_cop_stats()    → Aggregates            │
│                                                 │
│  Resources:                                     │
│  ├─ cop://entities                             │
│  ├─ cop://entities/{id}                        │
│  └─ cop://stats                                │
│                                                 │
│  State:                                         │
│  └─ COPState (in-memory, thread-safe)          │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 🛠️ Tools

### `find_duplicates`

Find potential duplicate entities using spatial and temporal proximity.

**Algorithm:**
1. Haversine distance between locations
2. Time window comparison
3. Entity type matching
4. Combined score (70% spatial, 30% temporal)

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `entity` | object | required | EntityCOP to check |
| `distance_threshold_m` | number | 500 | Max distance in meters |
| `time_window_sec` | number | 300 | Max time difference in seconds |

**Returns:**
```json
{
  "matches": [
    {
      "entity_id": "aircraft_001",
      "distance_m": 142.5,
      "time_diff_sec": 30.0,
      "score": 0.85
    }
  ],
  "thresholds": {"distance_m": 500, "time_window_sec": 300}
}
```

---

### `merge_entities`

Merge two entities into a single fused entity.

**Fusion Logic:**
- **Location**: Weighted average by confidence
- **Confidence**: Boosted (+0.1) for multi-sensor fusion
- **Sensors**: Combined list from both entities
- **Metadata**: Merged (newer values take precedence)
- **Classification**: Higher security level preserved

**Parameters:**
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `entity1_id` | string | required | First entity ID |
| `entity2_id` | string | required | Second entity ID |
| `keep_id` | string | entity1_id | Which ID to keep |

**Returns:**
```json
{
  "merged_entity": {...},
  "removed_entity_id": "aircraft_002",
  "sensors_combined": ["radar_01", "radar_02"],
  "confidence_after_merge": 0.9
}
```

---

### `update_cop`

Batch add or update entities in the COP.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `entities` | array | List of EntityCOP objects |

**Returns:**
```json
{
  "added": 3,
  "updated": 1,
  "errors": [],
  "total_entities_in_cop": 15
}
```

---

### `query_cop`

Query entities with filters.

**Parameters:**
| Name | Type | Description |
|------|------|-------------|
| `entity_type` | string | Filter by type (aircraft, ship, etc.) |
| `classification` | string | Filter by IFF (friendly, hostile, etc.) |
| `bbox` | array | Bounding box [min_lat, min_lon, max_lat, max_lon] |
| `since_timestamp` | string | ISO timestamp for time filter |
| `min_confidence` | number | Minimum confidence (0.0-1.0) |
| `limit` | integer | Max results (default: 100) |

**Returns:**
```json
{
  "entities": [...],
  "count": 5,
  "total_in_cop": 15,
  "filters_applied": {...}
}
```

---

### `get_cop_stats`

Get aggregate statistics about the COP.

**Returns:**
```json
{
  "total_entities": 15,
  "by_type": {"aircraft": 8, "ship": 5, "uav": 2},
  "by_classification": {"unknown": 10, "friendly": 5},
  "unique_sensors": 6,
  "average_confidence": 0.82
}
```

---

## 📂 Files

| File | Description |
|------|-------------|
| `server.py` | MCP server entry point with tool/resource definitions |
| `state.py` | Thread-safe COP state management (in-memory) |
| `tools.py` | Tool implementations (find, merge, update, query) |

---

## 🚀 Running the Server

### Standalone (stdio)

```bash
uv run python -m src.mcp_servers.cop_fusion.server
```

### With MCP Inspector

```bash
npx @anthropic/mcp-inspector uv run python -m src.mcp_servers.cop_fusion.server
```

### Claude Desktop Configuration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cop-fusion": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp_servers.cop_fusion.server"],
      "cwd": "/path/to/copforge"
    }
  }
}
```

---

## 🔭 Telemetry

All operations are traced with OpenTelemetry:

```python
tracer = get_tracer("copforge.mcp.cop_fusion.tools")

with traced_operation(tracer, "find_duplicates", {...}) as span:
    # ... operation logic
    span.set_attribute("cop.matches_found", len(matches))
```

---

## 🧪 Tests

```bash
# Run COP Fusion tests
uv run pytest tests/mcp_servers/test_cop_fusion.py -v

# With coverage
uv run pytest tests/mcp_servers/ --cov=src/mcp_servers/cop_fusion
```

---

## 🔮 Future: Persistent Storage

The current implementation uses in-memory storage. For production, extend `COPState` to use:

- **PostgreSQL + PostGIS**: For spatial queries and persistence
- **Redis**: For real-time caching and pub/sub updates

```python
# Future interface (not yet implemented)
class PersistentCOPState(COPState):
    def __init__(self, db_url: str):
        self.db = AsyncDatabase(db_url)

    async def add_entity(self, entity: EntityCOP) -> bool:
        await self.db.execute(...)
```
