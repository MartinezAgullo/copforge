"""
MCP Client for CopForge.

Async client to communicate with MCP servers via stdio subprocess.
Uses the official MCP SDK client implementation.
"""

import ast
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.core.telemetry import get_tracer, traced_operation

logger = logging.getLogger(__name__)
tracer = get_tracer("copforge.mcp_client")


class MCPClientError(Exception):
    """Exception raised for MCP client errors."""


class CopFusionClient:
    """
    Client for the COP Fusion MCP Server.

    Manages subprocess lifecycle and provides typed methods for each tool.

    Usage:
        async with CopFusionClient() as client:
            result = await client.update_cop(entities)
            stats = await client.get_cop_stats()
    """

    def __init__(
        self,
        server_command: str = "python",
        server_args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """
        Initialize COP Fusion client.

        Args:
            server_command: Command to run the MCP server.
            server_args: Arguments for the server command.
            env: Environment variables for the subprocess.
        """
        self.server_params = StdioServerParameters(
            command=server_command,
            args=server_args or ["-m", "src.mcp_servers.cop_fusion.server"],
            env=env,
        )
        self._session: ClientSession | None = None
        self._stdio_context: Any = None
        self._session_context: Any = None

    async def __aenter__(self) -> "CopFusionClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """Establish connection to the MCP server."""
        with traced_operation(tracer, "mcp_client_connect") as span:
            logger.info("Connecting to COP Fusion MCP Server...")

            self._stdio_context = stdio_client(self.server_params)
            read, write = await self._stdio_context.__aenter__()

            self._session_context = ClientSession(read, write)
            self._session = await self._session_context.__aenter__()

            # Initialize the session
            await self._session.initialize()
            span.set_attribute("mcp.connected", True)
            logger.info("Connected to COP Fusion MCP Server")

    async def disconnect(self) -> None:
        """Close connection to the MCP server."""
        if self._session_context:
            await self._session_context.__aexit__(None, None, None)
        if self._stdio_context:
            await self._stdio_context.__aexit__(None, None, None)
        self._session = None
        logger.info("Disconnected from COP Fusion MCP Server")

    @property
    def session(self) -> ClientSession:
        """Get the active session, raising if not connected."""
        if self._session is None:
            raise MCPClientError("Not connected. Use 'async with' or call connect() first.")
        return self._session

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """
        Call an MCP tool and return the result.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Parsed result dictionary.
        """
        with traced_operation(tracer, f"mcp_call_{name}", {"tool": name}) as span:
            result = await self.session.call_tool(name, arguments)

            # Extract text content from result
            if result.content and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, "text"):
                    # Parse the result - it's returned as a string repr of dict
                    text: str = content.text
                    try:
                        # Try to parse as JSON first
                        parsed: dict[str, Any] = json.loads(text)
                        span.set_attribute("tool.success", "error" not in parsed)
                        return parsed
                    except json.JSONDecodeError:
                        # Fall back to ast.literal_eval for dict repr
                        try:
                            parsed = ast.literal_eval(text)
                            if isinstance(parsed, dict):
                                span.set_attribute("tool.success", "error" not in parsed)
                                return parsed
                            span.set_attribute("tool.success", False)
                            return {"raw_response": text, "parsed_type": type(parsed).__name__}
                        except (ValueError, SyntaxError):
                            span.set_attribute("tool.success", False)
                            return {"raw_response": text}
            span.set_attribute("tool.success", False)
            return {"error": "Empty response"}

    # =========================================================================
    # Typed Tool Methods
    # =========================================================================

    async def find_duplicates(
        self,
        entity: dict[str, Any],
        distance_threshold_m: float = 500,
        time_window_sec: float = 300,
    ) -> dict[str, Any]:
        """
        Find potential duplicate entities in the COP.

        Args:
            entity: Entity data to check for duplicates.
            distance_threshold_m: Maximum distance in meters.
            time_window_sec: Maximum time difference in seconds.

        Returns:
            Dict with matches and scores.
        """
        return await self.call_tool(
            "find_duplicates",
            {
                "entity": entity,
                "distance_threshold_m": distance_threshold_m,
                "time_window_sec": time_window_sec,
            },
        )

    async def merge_entities(
        self,
        entity1_id: str,
        entity2_id: str,
        keep_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Merge two entities into one.

        Args:
            entity1_id: First entity ID.
            entity2_id: Second entity ID.
            keep_id: Which ID to keep (optional).

        Returns:
            Merged entity data.
        """
        args: dict[str, Any] = {
            "entity1_id": entity1_id,
            "entity2_id": entity2_id,
        }
        if keep_id:
            args["keep_id"] = keep_id
        return await self.call_tool("merge_entities", args)

    async def update_cop(self, entities: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Add or update entities in the COP.

        Args:
            entities: List of entity data dicts.

        Returns:
            Stats about added/updated entities.
        """
        return await self.call_tool("update_cop", {"entities": entities})

    async def query_cop(
        self,
        entity_type: str | None = None,
        classification: str | None = None,
        bbox: list[float] | None = None,
        since_timestamp: str | None = None,
        min_confidence: float | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Query entities from the COP.

        Args:
            entity_type: Filter by entity type.
            classification: Filter by IFF classification.
            bbox: Bounding box [min_lat, min_lon, max_lat, max_lon].
            since_timestamp: Filter entities after this time (ISO format).
            min_confidence: Minimum confidence threshold.
            limit: Maximum results to return.

        Returns:
            List of matching entities.
        """
        args: dict[str, Any] = {"limit": limit}
        if entity_type:
            args["entity_type"] = entity_type
        if classification:
            args["classification"] = classification
        if bbox:
            args["bbox"] = bbox
        if since_timestamp:
            args["since_timestamp"] = since_timestamp
        if min_confidence:
            args["min_confidence"] = min_confidence
        return await self.call_tool("query_cop", args)

    async def get_cop_stats(self) -> dict[str, Any]:
        """
        Get COP statistics.

        Returns:
            Statistics about entities in COP.
        """
        return await self.call_tool("get_cop_stats", {})

    async def sync_to_mapa(self) -> dict[str, Any]:
        """
        Push all entities to mapa-puntos-interes.

        Returns:
            Sync statistics.
        """
        return await self.call_tool("sync_to_mapa", {})

    async def load_from_mapa(self) -> dict[str, Any]:
        """
        Pull all entities from mapa-puntos-interes.

        Returns:
            Load statistics.
        """
        return await self.call_tool("load_from_mapa", {})

    async def check_mapa_connection(self) -> dict[str, Any]:
        """
        Check connection to mapa-puntos-interes server.

        Returns:
            Connection status.
        """
        return await self.call_tool("check_mapa_connection", {})

    async def list_tools(self) -> list[str]:
        """
        List available tools in the MCP server.

        Returns:
            List of tool names.
        """
        result = await self.session.list_tools()
        return [tool.name for tool in result.tools]


@asynccontextmanager
async def get_cop_fusion_client(
    server_command: str = "python",
    server_args: list[str] | None = None,
) -> Any:
    """
    Context manager for COP Fusion client.

    Usage:
        async with get_cop_fusion_client() as client:
            await client.update_cop(entities)
    """
    client = CopFusionClient(server_command, server_args)
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()
