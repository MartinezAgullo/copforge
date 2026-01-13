"""
MCP Server: COP Fusion - Deterministic tools for COP operations with mapa sync.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool

from src.core.telemetry import get_tracer, traced_operation
from src.mcp_servers.cop_fusion.state import get_cop_state
from src.mcp_servers.cop_fusion.tools import (
    check_mapa_connection,
    find_duplicates,
    get_cop_stats,
    load_from_mapa,
    merge_entities,
    query_cop,
    sync_to_mapa,
    update_cop,
)

logger = logging.getLogger(__name__)
tracer = get_tracer("copforge.mcp.cop_fusion")


@asynccontextmanager
async def lifespan(_server: Server) -> AsyncIterator[None]:
    """Manage server lifecycle."""
    logger.info("COP Fusion MCP Server starting...")
    cop_state = get_cop_state(auto_sync=True, auto_load=False)
    is_connected, msg = cop_state.check_mapa_connection()
    if is_connected:
        logger.info(f"Connected to mapa: {msg}")
        result = cop_state.load_from_mapa()
        logger.info(f"Loaded {result.get('loaded', 0)} entities from mapa")
    else:
        logger.warning(f"mapa not available: {msg}")
    logger.info(f"COP initialized with {len(cop_state.entities)} entities")
    yield
    logger.info("COP Fusion MCP Server shutting down...")


app = Server("cop-fusion")
ListToolsHandler = Callable[[], Awaitable[list[Tool]]]
CallToolHandler = Callable[[str, dict[str, Any]], Awaitable[list[TextContent]]]
ListResourcesHandler = Callable[[], Awaitable[list[Resource]]]
ReadResourceHandler = Callable[[str], Awaitable[str]]

_list_tools = cast(Callable[[ListToolsHandler], ListToolsHandler], app.list_tools())
_call_tool = cast(Callable[[CallToolHandler], CallToolHandler], app.call_tool())
_list_resources = cast(Callable[[ListResourcesHandler], ListResourcesHandler], app.list_resources())
_read_resource = cast(Callable[[ReadResourceHandler], ReadResourceHandler], app.read_resource())


TOOLS = [
    Tool(
        name="find_duplicates",
        description="Find duplicate entities using Haversine distance and time window.",
        inputSchema={
            "type": "object",
            "properties": {
                "entity": {"type": "object"},
                "distance_threshold_m": {"type": "number", "default": 500},
                "time_window_sec": {"type": "number", "default": 300},
            },
            "required": ["entity"],
        },
    ),
    Tool(
        name="merge_entities",
        description="Merge two entities. Uses location from most recent timestamp.",
        inputSchema={
            "type": "object",
            "properties": {
                "entity1_id": {"type": "string"},
                "entity2_id": {"type": "string"},
                "keep_id": {"type": "string"},
            },
            "required": ["entity1_id", "entity2_id"],
        },
    ),
    Tool(
        name="update_cop",
        description="Add or update entities. Auto-syncs to mapa.",
        inputSchema={
            "type": "object",
            "properties": {"entities": {"type": "array", "items": {"type": "object"}}},
            "required": ["entities"],
        },
    ),
    Tool(
        name="query_cop",
        description="Query entities with filters.",
        inputSchema={
            "type": "object",
            "properties": {
                "entity_type": {"type": "string"},
                "classification": {"type": "string"},
                "bbox": {"type": "array"},
                "since_timestamp": {"type": "string"},
                "min_confidence": {"type": "number"},
                "limit": {"type": "integer", "default": 100},
            },
        },
    ),
    Tool(
        name="get_cop_stats",
        description="Get COP statistics.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="sync_to_mapa",
        description="Push all entities to mapa.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="load_from_mapa",
        description="Pull all entities from mapa.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="check_mapa_connection",
        description="Check mapa server connection.",
        inputSchema={"type": "object", "properties": {}},
    ),
]


@_list_tools
async def list_tools() -> list[Tool]:
    return TOOLS


@_call_tool
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    with traced_operation(tracer, f"mcp_tool_{name}", {"tool": name}) as span:
        try:
            cop_state = get_cop_state()
            result: dict[str, Any]
            if name == "find_duplicates":
                result = find_duplicates(
                    cop_state,
                    arguments["entity"],
                    arguments.get("distance_threshold_m", 500),
                    arguments.get("time_window_sec", 300),
                )
            elif name == "merge_entities":
                result = merge_entities(
                    cop_state,
                    arguments["entity1_id"],
                    arguments["entity2_id"],
                    arguments.get("keep_id"),
                )
            elif name == "update_cop":
                result = update_cop(cop_state, arguments["entities"])
            elif name == "query_cop":
                result = query_cop(
                    cop_state,
                    arguments.get("entity_type"),
                    arguments.get("classification"),
                    arguments.get("bbox"),
                    arguments.get("since_timestamp"),
                    arguments.get("min_confidence"),
                    arguments.get("limit", 100),
                )
            elif name == "get_cop_stats":
                result = get_cop_stats(cop_state)
            elif name == "sync_to_mapa":
                result = sync_to_mapa(cop_state)
            elif name == "load_from_mapa":
                result = load_from_mapa(cop_state)
            elif name == "check_mapa_connection":
                result = check_mapa_connection(cop_state)
            else:
                result = {"error": f"Unknown tool: {name}"}
            span.set_attribute("tool.success", "error" not in result)
            return [TextContent(type="text", text=str(result))]
        except Exception as e:
            logger.exception(f"Error in tool {name}")
            span.set_attribute("tool.error", str(e))
            return [TextContent(type="text", text=f"Error: {e!s}")]


RESOURCES = [
    Resource(uri="cop://entities", name="COP Entities", mimeType="application/json"),
    Resource(
        uri="cop://entities/{entity_id}", name="COP Entity by ID", mimeType="application/json"
    ),
    Resource(uri="cop://stats", name="COP Statistics", mimeType="application/json"),
]


@_list_resources
async def list_resources() -> list[Resource]:
    return RESOURCES


@_read_resource
async def read_resource(uri: str) -> str:
    cop_state = get_cop_state()
    if uri == "cop://entities":
        return json.dumps(
            {eid: e.model_dump_json_safe() for eid, e in cop_state.entities.items()}, indent=2
        )
    elif uri.startswith("cop://entities/"):
        entity_id = uri.replace("cop://entities/", "")
        entity = cop_state.entities.get(entity_id)
        return json.dumps(
            entity.model_dump_json_safe() if entity else {"error": f"Not found: {entity_id}"},
            indent=2,
        )
    elif uri == "cop://stats":
        return json.dumps(get_cop_stats(cop_state), indent=2)
    return json.dumps({"error": f"Unknown resource: {uri}"})


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting COP Fusion MCP Server...")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
