# MCP Server: COP Fusion

Deterministic MCP server for COP operations with bidirectional sync to mapa-puntos-interes.

## Architecture

```bash
                          ┌─────────────────────────┐
                          │   mapa-puntos-interes   │
                          │   (Source of Truth)     │
                          └───────────┬─────────────┘
                                      │
                          ┌───────────▼─────────────┐
                          │      MapaClient         │
                          │  (HTTP REST client)     │
                          └───────────┬─────────────┘
                                      │
┌─────────────────────────────────────▼─────────────────────────────────────┐
│                         MCP SERVER: COP FUSION                            │
│                                                                           │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────────┐    │
│  │   COPSync   │◄──►│  COPState   │◄──►│          TOOLS              │    │
│  │  (sync mgr) │    │  (cache)    │    │  • find_duplicates          │    │
│  └─────────────┘    └─────────────┘    │  • merge_entities           │    │
│                                        │  • update_cop               │    │
│  LIFECYCLE:                            │  • query_cop                │    │
│  • startup: load_from_mapa()           │  • get_cop_stats            │    │
│  • operation: COPState as fast cache   │  • sync_to_mapa             │    │
│  • persist: auto-sync on changes       │  • load_from_mapa           │    │
│                                        │  • check_mapa_connection    │    │
│                                        └─────────────────────────────┘    │
└───────────────────────────────────────────────────────────────────────────┘
```

## Tools

| Tool | Description |
|------|-------------|
| `find_duplicates` | Find duplicate entities (Haversine + time window + classification) |
| `merge_entities` | Merge two entities (**uses location from most recent timestamp**) |
| `update_cop` | Add/update entities (auto-syncs to mapa) |
| `query_cop` | Query with filters (type, classification, bbox, time, confidence) |
| `get_cop_stats` | Get COP statistics including sync status |
| `sync_to_mapa` | Manual full sync to mapa-puntos-interes |
| `load_from_mapa` | Pull entities from mapa into cache |
| `check_mapa_connection` | Health check for mapa server |

## Key Behaviors

### Merge Strategy
When merging two entities, the **location from the entity with the most recent timestamp** is used (not weighted average).

### Duplicate Detection
Entities are considered potential duplicates if:
1. Same `entity_type`
2. Same `classification` (friendly, hostile, etc.)
3. Distance ≤ threshold (default: 500m)
4. Time difference ≤ window (default: 300s)

### Sync Strategy
- **On startup**: Load from mapa-puntos-interes
- **On update/add**: Auto-sync to mapa (if enabled)
- **On remove**: Auto-delete from mapa (if enabled)

## Files

| File | Description |
|------|-------------|
| `server.py` | MCP server entry point |
| `state.py` | COPState with mapa integration |
| `tools.py` | Tool implementations |
| `cop_sync.py` | Sync manager (COPState ↔ mapa) |
| `mapa_client.py` | HTTP client for mapa API |

## Running

```bash
# Standalone
uv run python -m src.mcp_servers.cop_fusion.server

# With MCP Inspector
npx @anthropic/mcp-inspector uv run python -m src.mcp_servers.cop_fusion.server
```

## Configuration

Environment variables:
- `MAPA_BASE_URL`: mapa-puntos-interes URL (default: http://localhost:3000)

## Tests

```bash
uv run pytest tests/mcp_servers/test_cop_fusion.py -v
```
