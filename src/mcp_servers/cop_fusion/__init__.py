"""
MCP Server: COP Fusion

Deterministic tools for Common Operational Picture operations.
"""

from src.mcp_servers.cop_fusion.server import app, main
from src.mcp_servers.cop_fusion.state import COPState, get_cop_state, reset_cop_state
from src.mcp_servers.cop_fusion.tools import (
    find_duplicates,
    get_cop_stats,
    haversine_distance,
    merge_entities,
    query_cop,
    update_cop,
)

__all__ = [
    # Server
    "app",
    "main",
    # State
    "COPState",
    "get_cop_state",
    "reset_cop_state",
    # Tools
    "find_duplicates",
    "merge_entities",
    "update_cop",
    "query_cop",
    "get_cop_stats",
    "haversine_distance",
]
