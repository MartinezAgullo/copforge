"""
COP Synchronization - Syncs COPState with mapa-puntos-interes.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.core.telemetry import get_tracer, traced_operation
from src.mcp_servers.cop_fusion.mapa_client import MapaClient, MapaClientError, get_mapa_client
from src.models.cop import EntityCOP, Location

logger = logging.getLogger(__name__)
tracer = get_tracer("copforge.mcp.cop_fusion.sync")


class COPSyncError(Exception):
    """Exception raised for COP sync errors."""


# Entity type mappings
ENTITY_TYPE_TO_MAPA = {
    "aircraft": "aeronave",
    "fighter": "aeronave",
    "bomber": "aeronave",
    "helicopter": "helicoptero",
    "uav": "dron",
    "missile": "misil",
    "ground_vehicle": "vehiculo",
    "tank": "tanque",
    "apc": "vehiculo_blindado",
    "artillery": "artilleria",
    "infantry": "infanteria",
    "ship": "barco",
    "destroyer": "destructor",
    "submarine": "submarino",
    "base": "base",
    "building": "edificio",
    "infrastructure": "infraestructura",
    "person": "persona",
    "event": "evento",
    "unknown": "desconocido",
}
MAPA_TO_ENTITY_TYPE = {v: k for k, v in ENTITY_TYPE_TO_MAPA.items()}

CLASSIFICATION_TO_MAPA = {
    "friendly": "amigo",
    "hostile": "enemigo",
    "neutral": "neutral",
    "unknown": "desconocido",
}
MAPA_TO_CLASSIFICATION = {v: k for k, v in CLASSIFICATION_TO_MAPA.items()}


def entity_to_punto(entity: EntityCOP) -> dict[str, Any]:
    """Convert EntityCOP to mapa punto format."""
    return {
        "elemento_identificado": entity.entity_id,
        "nombre": f"{entity.entity_type}_{entity.entity_id[:8]}",
        "tipo_elemento": ENTITY_TYPE_TO_MAPA.get(entity.entity_type, "desconocido"),
        "latitud": entity.location.lat,
        "longitud": entity.location.lon,
        "altitud": entity.location.alt,
        "rumbo": entity.heading,
        "velocidad": entity.speed_kmh,
        "clasificacion": CLASSIFICATION_TO_MAPA.get(entity.classification, "desconocido"),
        "nivel_clasificacion": entity.information_classification,
        "confianza": entity.confidence,
        "sensores": ",".join(entity.source_sensors) if entity.source_sensors else None,
        "timestamp": entity.timestamp.isoformat(),
        "comentarios": entity.comments,
        "metadata": entity.metadata,
    }


def punto_to_entity(punto: dict[str, Any]) -> EntityCOP:
    """Convert mapa punto to EntityCOP."""
    timestamp_str = punto.get("timestamp")
    try:
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str
            else datetime.now(UTC)
        )
    except ValueError:
        timestamp = datetime.now(UTC)

    sensores_str = punto.get("sensores", "")
    source_sensors = sensores_str.split(",") if sensores_str else []
    tipo_elemento = punto.get("tipo_elemento", "desconocido")
    entity_type = MAPA_TO_ENTITY_TYPE.get(tipo_elemento, "unknown")
    clasificacion = punto.get("clasificacion", "desconocido")
    classification = MAPA_TO_CLASSIFICATION.get(clasificacion, "unknown")

    return EntityCOP(
        entity_id=punto.get("elemento_identificado", f"mapa_{punto.get('id', 'unknown')}"),
        entity_type=entity_type,
        location=Location(
            lat=punto.get("latitud", 0.0), lon=punto.get("longitud", 0.0), alt=punto.get("altitud")
        ),
        heading=punto.get("rumbo"),
        speed_kmh=punto.get("velocidad"),
        classification=classification,
        information_classification=punto.get("nivel_clasificacion", "UNCLASSIFIED"),
        confidence=punto.get("confianza", 0.5),
        timestamp=timestamp,
        source_sensors=source_sensors,
        metadata=punto.get("metadata", {}),
        comments=punto.get("comentarios"),
    )


class COPSync:
    """Synchronizes CopForge COP with mapa-puntos-interes."""

    def __init__(
        self, mapa_client: MapaClient | None = None, mapa_base_url: str = "http://localhost:3000"
    ) -> None:
        self.client = mapa_client or get_mapa_client(base_url=mapa_base_url)
        self.last_sync: datetime | None = None
        self.is_connected = False
        self.sync_stats = {
            "total_syncs": 0,
            "total_created": 0,
            "total_updated": 0,
            "total_deleted": 0,
            "total_errors": 0,
            "total_loaded": 0,
        }

    def check_connection(self) -> tuple[bool, str]:
        is_healthy, msg = self.client.health_check()
        self.is_connected = is_healthy
        return is_healthy, msg

    def load_from_mapa(self) -> tuple[list[EntityCOP], dict[str, Any]]:
        with traced_operation(tracer, "load_from_mapa") as span:
            entities: list[EntityCOP] = []
            errors: list[str] = []
            try:
                puntos = self.client.get_all_puntos()
                for punto in puntos:
                    try:
                        entity = punto_to_entity(punto)
                        entities.append(entity)
                    except Exception as e:
                        errors.append(f"punto_{punto.get('id', 'unknown')}: {e!s}")
                self.sync_stats["total_loaded"] += len(entities)
                span.set_attribute("sync.loaded", len(entities))
                return entities, {
                    "loaded": len(entities),
                    "errors": errors,
                    "total_in_mapa": len(puntos),
                }
            except MapaClientError as e:
                logger.error(f"Failed to load from mapa: {e}")
                return [], {"loaded": 0, "errors": [str(e)], "total_in_mapa": 0}

    def sync_entity(self, entity: EntityCOP) -> tuple[bool, str]:
        with traced_operation(tracer, "sync_entity", {"entity_id": entity.entity_id}) as span:
            try:
                punto_data = entity_to_punto(entity)
                punto, was_created = self.client.upsert_punto(punto_data)
                if was_created:
                    self.sync_stats["total_created"] += 1
                    action = "created"
                else:
                    self.sync_stats["total_updated"] += 1
                    action = "updated"
                span.set_attribute("sync.action", action)
                return True, f"Entity {entity.entity_id} {action} in mapa (id={punto['id']})"
            except Exception as e:
                self.sync_stats["total_errors"] += 1
                return False, f"Failed to sync entity {entity.entity_id}: {e!s}"

    def sync_batch(self, entities: list[EntityCOP]) -> dict[str, Any]:
        with traced_operation(tracer, "sync_batch", {"count": len(entities)}) as span:
            if not entities:
                return {
                    "success": True,
                    "count": 0,
                    "created": 0,
                    "updated": 0,
                    "failed": 0,
                    "errors": [],
                }
            puntos_data = []
            conversion_errors: list[str] = []
            for entity in entities:
                try:
                    puntos_data.append(entity_to_punto(entity))
                except Exception as e:
                    conversion_errors.append(f"{entity.entity_id}: {e!s}")
            try:
                stats = self.client.batch_upsert(puntos_data)
                self.sync_stats["total_created"] += stats["created"]
                self.sync_stats["total_updated"] += stats["updated"]
                self.sync_stats["total_errors"] += stats["failed"]
                self.sync_stats["total_syncs"] += 1
                self.last_sync = datetime.now(UTC)
                span.set_attribute("sync.created", stats["created"])
                return {
                    "success": True,
                    "count": len(entities),
                    "created": stats["created"],
                    "updated": stats["updated"],
                    "failed": stats["failed"] + len(conversion_errors),
                    "errors": stats["errors"] + conversion_errors,
                }
            except Exception as e:
                return {
                    "success": False,
                    "count": len(entities),
                    "created": 0,
                    "updated": 0,
                    "failed": len(entities),
                    "errors": [f"Batch sync failed: {e!s}"] + conversion_errors,
                }

    def remove_entity(self, entity_id: str) -> tuple[bool, str]:
        with traced_operation(tracer, "remove_entity", {"entity_id": entity_id}) as span:
            try:
                punto = self.client.find_by_elemento_identificado(entity_id)
                if not punto:
                    return True, f"Entity {entity_id} not found in mapa"
                success = self.client.delete_punto(punto["id"])
                if success:
                    self.sync_stats["total_deleted"] += 1
                    span.set_attribute("sync.deleted", True)
                    return True, f"Entity {entity_id} removed from mapa"
                return False, f"Failed to delete entity {entity_id}"
            except Exception as e:
                self.sync_stats["total_errors"] += 1
                return False, f"Failed to remove entity {entity_id}: {e!s}"

    def get_sync_stats(self) -> dict[str, Any]:
        return {
            **self.sync_stats,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "is_connected": self.is_connected,
        }


_cop_sync: COPSync | None = None


def get_cop_sync(mapa_base_url: str = "http://localhost:3000") -> COPSync:
    global _cop_sync
    if _cop_sync is None:
        _cop_sync = COPSync(mapa_base_url=mapa_base_url)
    return _cop_sync


def reset_cop_sync() -> None:
    global _cop_sync
    _cop_sync = None
