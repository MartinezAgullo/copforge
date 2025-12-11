"""
MCP Server: COP Fusion

Deterministic tools for Common Operational Picture operations:
- Duplicate detection (Haversine distance + time window)
- Entity merging (sensor fusion)
- COP state management (in-memory or persistent)
- Querying and filtering

This server exposes MCP tools that agents can invoke for COP operations.
All operations are deterministic (no LLM calls).
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

from src.core.telemetry import get_tracer, traced_operation
from src.mcp_servers.cop_fusion.state import get_cop_state
from src.mcp_servers.cop_fusion.tools import (
    find_duplicates,
    get_cop_stats,
    merge_entities,
    query_cop,
    update_cop,
)

# =============================================================================
# Configuration
# =============================================================================

logger = logging.getLogger(__name__)
tracer = get_tracer("copforge.mcp.cop_fusion")

# =============================================================================
# MCP Server Setup
# =============================================================================


@asynccontextmanager
async def lifespan(_server: Server) -> AsyncIterator[None]:
    """Manage server lifecycle."""
    logger.info("COP Fusion MCP Server starting...")
    cop_state = get_cop_state()
    logger.info(f"COP State initialized with {len(cop_state.entities)} entities")
    yield
    logger.info("COP Fusion MCP Server shutting down...")


# Create MCP server instance
app = Server("cop-fusion")


# =============================================================================
# Tool Definitions
# =============================================================================

TOOLS = [
    Tool(
        name="find_duplicates",
        description="""Find potential duplicate entities in the COP.

Uses Haversine distance and time window to identify entities that may
represent the same real-world object. Returns matches with similarity scores.

Parameters:
- entity: EntityCOP to check for duplicates (JSON object)
- distance_threshold_m: Maximum distance in meters (default: 500)
- time_window_sec: Maximum time difference in seconds (default: 300)

Returns: List of matches with entity_id, distance_m, time_diff_sec, score""",
        inputSchema={
            "type": "object",
            "properties": {
                "entity": {
                    "type": "object",
                    "description": "EntityCOP to check for duplicates",
                },
                "distance_threshold_m": {
                    "type": "number",
                    "description": "Max distance in meters",
                    "default": 500,
                },
                "time_window_sec": {
                    "type": "number",
                    "description": "Max time difference in seconds",
                    "default": 300,
                },
            },
            "required": ["entity"],
        },
    ),
    Tool(
        name="merge_entities",
        description="""Merge two entities into a single fused entity.

Combines information from both entities:
- Location: Weighted average by confidence
- Confidence: Boosted based on sensor fusion
- Sensors: Combined list from both entities
- Metadata: Merged with newer values taking precedence

Parameters:
- entity1_id: ID of first entity in COP
- entity2_id: ID of second entity in COP
- keep_id: Which entity ID to keep (default: entity1_id)

Returns: Merged EntityCOP""",
        inputSchema={
            "type": "object",
            "properties": {
                "entity1_id": {
                    "type": "string",
                    "description": "ID of first entity",
                },
                "entity2_id": {
                    "type": "string",
                    "description": "ID of second entity",
                },
                "keep_id": {
                    "type": "string",
                    "description": "Which ID to keep for merged entity",
                },
            },
            "required": ["entity1_id", "entity2_id"],
        },
    ),
    Tool(
        name="update_cop",
        description="""Add or update entities in the COP.

For each entity:
- If entity_id exists: Updates the existing entity
- If entity_id is new: Adds the entity to COP

Parameters:
- entities: List of EntityCOP objects to add/update

Returns: Statistics about the operation (added, updated, errors)""",
        inputSchema={
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of EntityCOP objects",
                },
            },
            "required": ["entities"],
        },
    ),
    Tool(
        name="query_cop",
        description="""Query entities from the COP with filters.

Supports filtering by:
- entity_type: Filter by type (aircraft, uav, ship, etc.)
- classification: Filter by IFF (friendly, hostile, neutral, unknown)
- bbox: Bounding box [min_lat, min_lon, max_lat, max_lon]
- since_timestamp: Only entities updated after this time (ISO format)
- min_confidence: Minimum confidence threshold (0.0-1.0)
- limit: Maximum number of results

Returns: List of matching EntityCOP objects""",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "description": "Filter by entity type",
                },
                "classification": {
                    "type": "string",
                    "description": "Filter by IFF classification",
                },
                "bbox": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Bounding box [min_lat, min_lon, max_lat, max_lon]",
                },
                "since_timestamp": {
                    "type": "string",
                    "description": "ISO timestamp for time filter",
                },
                "min_confidence": {
                    "type": "number",
                    "description": "Minimum confidence (0.0-1.0)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 100,
                },
            },
        },
    ),
    Tool(
        name="get_cop_stats",
        description="""Get statistics about the current COP state.

Returns counts by entity type, classification, sensor sources,
and other aggregate information about the operational picture.

No parameters required.""",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]


@app.list_tools()  # type: ignore
async def list_tools() -> list[Tool]:
    """List available tools."""
    return TOOLS


@app.call_tool()  # type: ignore
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool invocations."""
    with traced_operation(tracer, f"mcp_tool_{name}", {"tool": name}) as span:
        try:
            cop_state = get_cop_state()

            if name == "find_duplicates":
                result = find_duplicates(
                    cop_state=cop_state,
                    entity_data=arguments["entity"],
                    distance_threshold_m=arguments.get("distance_threshold_m", 500),
                    time_window_sec=arguments.get("time_window_sec", 300),
                )

            elif name == "merge_entities":
                result = merge_entities(
                    cop_state=cop_state,
                    entity1_id=arguments["entity1_id"],
                    entity2_id=arguments["entity2_id"],
                    keep_id=arguments.get("keep_id"),
                )

            elif name == "update_cop":
                result = update_cop(
                    cop_state=cop_state,
                    entities_data=arguments["entities"],
                )

            elif name == "query_cop":
                result = query_cop(
                    cop_state=cop_state,
                    entity_type=arguments.get("entity_type"),
                    classification=arguments.get("classification"),
                    bbox=arguments.get("bbox"),
                    since_timestamp=arguments.get("since_timestamp"),
                    min_confidence=arguments.get("min_confidence"),
                    limit=arguments.get("limit", 100),
                )

            elif name == "get_cop_stats":
                result = get_cop_stats(cop_state=cop_state)

            else:
                result = {"error": f"Unknown tool: {name}"}

            span.set_attribute("tool.success", "error" not in result)
            return [TextContent(type="text", text=str(result))]

        except Exception as e:
            logger.exception(f"Error in tool {name}")
            span.set_attribute("tool.success", False)
            span.set_attribute("tool.error", str(e))
            return [TextContent(type="text", text=f"Error: {e!s}")]


# =============================================================================
# Resource Definitions (COP State Access)
# =============================================================================

RESOURCES = [
    Resource(
        uri="cop://entities",
        name="COP Entities",
        description="All entities in the Common Operational Picture",
        mimeType="application/json",
    ),
    Resource(
        uri="cop://entities/{entity_id}",
        name="COP Entity by ID",
        description="Get a specific entity by ID",
        mimeType="application/json",
    ),
    Resource(
        uri="cop://stats",
        name="COP Statistics",
        description="Aggregate statistics about the COP",
        mimeType="application/json",
    ),
]


@app.list_resources()  # type: ignore
async def list_resources() -> list[Resource]:
    """List available resources."""
    return RESOURCES


@app.read_resource()  # type: ignore
async def read_resource(uri: str) -> str:
    """Read a resource by URI."""
    import json

    cop_state = get_cop_state()

    if uri == "cop://entities":
        entities = {eid: e.model_dump_json_safe() for eid, e in cop_state.entities.items()}
        return json.dumps(entities, indent=2)

    elif uri.startswith("cop://entities/"):
        entity_id = uri.replace("cop://entities/", "")
        if entity_id in cop_state.entities:
            return json.dumps(cop_state.entities[entity_id].model_dump_json_safe(), indent=2)
        return json.dumps({"error": f"Entity not found: {entity_id}"})

    elif uri == "cop://stats":
        stats = get_cop_stats(cop_state)
        return json.dumps(stats, indent=2)

    return json.dumps({"error": f"Unknown resource: {uri}"})


# =============================================================================
# Entry Point
# =============================================================================


async def main() -> None:
    """Run the MCP server."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting COP Fusion MCP Server...")

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
