"""
MCP Server: COP Fusion - Deterministic tools for COP operations with mapa sync.
"""

from src.mcp_servers.cop_fusion.cop_sync import COPSync, get_cop_sync, reset_cop_sync
from src.mcp_servers.cop_fusion.mapa_client import (
    MapaClient,
    MapaClientError,
    get_mapa_client,
    reset_mapa_client,
)
from src.mcp_servers.cop_fusion.server import app, main
from src.mcp_servers.cop_fusion.state import COPState, get_cop_state, reset_cop_state
from src.mcp_servers.cop_fusion.tools import (
    check_mapa_connection,
    find_duplicates,
    get_cop_stats,
    haversine_distance,
    load_from_mapa,
    merge_entities,
    query_cop,
    sync_to_mapa,
    update_cop,
)

__all__ = [
    "app",
    "main",
    "COPState",
    "get_cop_state",
    "reset_cop_state",
    "MapaClient",
    "MapaClientError",
    "get_mapa_client",
    "reset_mapa_client",
    "COPSync",
    "get_cop_sync",
    "reset_cop_sync",
    "find_duplicates",
    "merge_entities",
    "update_cop",
    "query_cop",
    "get_cop_stats",
    "sync_to_mapa",
    "load_from_mapa",
    "check_mapa_connection",
    "haversine_distance",
]
