"""
COP State Management with mapa-puntos-interes integration.
"""

import logging
from datetime import UTC, datetime
from threading import Lock
from typing import TYPE_CHECKING, Any

from src.core.telemetry import get_tracer, traced_operation
from src.models.cop import COPSnapshot, EntityCOP, ThreatAssessment

if TYPE_CHECKING:
    from src.mcp_servers.cop_fusion.cop_sync import COPSync

logger = logging.getLogger(__name__)
tracer = get_tracer("copforge.mcp.cop_fusion.state")


class COPState:
    """Thread-safe COP state with mapa-puntos-interes sync."""

    def __init__(
        self,
        mapa_base_url: str = "http://localhost:3000",
        auto_sync: bool = True,
        auto_load: bool = False,
    ) -> None:
        self._lock = Lock()
        self._entities: dict[str, EntityCOP] = {}
        self._threat_assessments: list[ThreatAssessment] = []
        self._snapshots: list[COPSnapshot] = []
        self._created_at = datetime.now(UTC)
        self._last_updated = self._created_at
        self._mapa_base_url = mapa_base_url
        self._auto_sync = auto_sync
        self._sync: COPSync | None = None
        self._mapa_connected = False
        if auto_load:
            self.load_from_mapa()

    @property
    def sync(self) -> "COPSync":
        if self._sync is None:
            from src.mcp_servers.cop_fusion.cop_sync import COPSync

            self._sync = COPSync(mapa_base_url=self._mapa_base_url)
        return self._sync

    @property
    def entities(self) -> dict[str, EntityCOP]:
        with self._lock:
            return self._entities.copy()

    @property
    def threat_assessments(self) -> list[ThreatAssessment]:
        with self._lock:
            return self._threat_assessments.copy()

    @property
    def is_mapa_connected(self) -> bool:
        return self._mapa_connected

    def check_mapa_connection(self) -> tuple[bool, str]:
        is_connected, msg = self.sync.check_connection()
        self._mapa_connected = is_connected
        return is_connected, msg

    def load_from_mapa(self) -> dict[str, Any]:
        with traced_operation(tracer, "load_from_mapa") as span:
            is_connected, msg = self.check_mapa_connection()
            if not is_connected:
                logger.warning(f"Cannot load from mapa: {msg}")
                return {"success": False, "error": msg, "loaded": 0}
            entities, stats = self.sync.load_from_mapa()
            with self._lock:
                self._entities.clear()
                for entity in entities:
                    self._entities[entity.entity_id] = entity
                self._last_updated = datetime.now(UTC)
            logger.info(f"Loaded {len(entities)} entities from mapa")
            span.set_attribute("mapa.loaded", len(entities))
            return {"success": True, "loaded": len(entities), "errors": stats.get("errors", [])}

    def _sync_to_mapa(self, entity: EntityCOP) -> None:
        if not self._auto_sync:
            return
        try:
            success, msg = self.sync.sync_entity(entity)
            if not success:
                logger.warning(f"Failed to sync to mapa: {msg}")
        except Exception as e:
            logger.warning(f"Error syncing to mapa: {e}")

    def _remove_from_mapa(self, entity_id: str) -> None:
        if not self._auto_sync:
            return
        try:
            success, msg = self.sync.remove_entity(entity_id)
            if not success:
                logger.warning(f"Failed to remove from mapa: {msg}")
        except Exception as e:
            logger.warning(f"Error removing from mapa: {e}")

    def get_entity(self, entity_id: str) -> EntityCOP | None:
        with self._lock:
            return self._entities.get(entity_id)

    def add_entity(self, entity: EntityCOP) -> bool:
        with traced_operation(tracer, "add_entity", {"entity_id": entity.entity_id}):
            with self._lock:
                if entity.entity_id in self._entities:
                    return False
                self._entities[entity.entity_id] = entity
                self._last_updated = datetime.now(UTC)
            self._sync_to_mapa(entity)
            return True

    def update_entity(self, entity: EntityCOP) -> bool:
        with traced_operation(tracer, "update_entity", {"entity_id": entity.entity_id}):
            with self._lock:
                if entity.entity_id not in self._entities:
                    return False
                self._entities[entity.entity_id] = entity
                self._last_updated = datetime.now(UTC)
            self._sync_to_mapa(entity)
            return True

    def upsert_entity(self, entity: EntityCOP) -> str:
        with traced_operation(tracer, "upsert_entity", {"entity_id": entity.entity_id}) as span:
            with self._lock:
                action = "updated" if entity.entity_id in self._entities else "added"
                self._entities[entity.entity_id] = entity
                self._last_updated = datetime.now(UTC)
                span.set_attribute("cop.action", action)
            self._sync_to_mapa(entity)
            return action

    def remove_entity(self, entity_id: str) -> bool:
        with traced_operation(tracer, "remove_entity", {"entity_id": entity_id}):
            with self._lock:
                if entity_id not in self._entities:
                    return False
                del self._entities[entity_id]
                self._last_updated = datetime.now(UTC)
            self._remove_from_mapa(entity_id)
            return True

    def add_threat_assessment(self, assessment: ThreatAssessment) -> None:
        with self._lock:
            self._threat_assessments.append(assessment)
            self._last_updated = datetime.now(UTC)

    def clear_threat_assessments(self) -> int:
        with self._lock:
            count = len(self._threat_assessments)
            self._threat_assessments.clear()
            return count

    def create_snapshot(self, snapshot_id: str | None = None) -> COPSnapshot:
        with traced_operation(tracer, "create_snapshot"), self._lock:
            now = datetime.now(UTC)
            sid = snapshot_id or f"snapshot_{now.strftime('%Y%m%d_%H%M%S')}"
            snapshot = COPSnapshot(
                snapshot_id=sid,
                timestamp=now,
                entities=self._entities.copy(),
                threat_assessments=self._threat_assessments.copy(),
                metadata={
                    "created_at": self._created_at.isoformat(),
                    "entity_count": len(self._entities),
                },
            )
            self._snapshots.append(snapshot)
            return snapshot

    def restore_snapshot(self, snapshot: COPSnapshot) -> None:
        with (
            traced_operation(tracer, "restore_snapshot", {"snapshot_id": snapshot.snapshot_id}),
            self._lock,
        ):
            self._entities = snapshot.entities.copy()
            self._threat_assessments = snapshot.threat_assessments.copy()
            self._last_updated = datetime.now(UTC)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            entities = list(self._entities.values())
            by_type: dict[str, int] = {}
            by_classification: dict[str, int] = {}
            sensors: set[str] = set()
            for e in entities:
                by_type[e.entity_type] = by_type.get(e.entity_type, 0) + 1
                by_classification[e.classification] = by_classification.get(e.classification, 0) + 1
                sensors.update(e.source_sensors)
            avg_confidence = (
                sum(e.confidence for e in entities) / len(entities) if entities else 0.0
            )
            sync_stats = self.sync.get_sync_stats() if self._sync else {}
            return {
                "total_entities": len(entities),
                "by_type": by_type,
                "by_classification": by_classification,
                "unique_sensors": len(sensors),
                "sensor_list": sorted(sensors),
                "average_confidence": round(avg_confidence, 3),
                "threat_assessments": len(self._threat_assessments),
                "snapshots_stored": len(self._snapshots),
                "created_at": self._created_at.isoformat(),
                "last_updated": self._last_updated.isoformat(),
                "mapa_connected": self._mapa_connected,
                "auto_sync_enabled": self._auto_sync,
                "sync_stats": sync_stats,
            }

    def sync_all_to_mapa(self) -> dict[str, Any]:
        with traced_operation(tracer, "sync_all_to_mapa") as span:
            entities = list(self.entities.values())
            result = self.sync.sync_batch(entities)
            span.set_attribute("sync.count", len(entities))
            return result

    def clear(self) -> dict[str, int]:
        with self._lock:
            counts = {
                "entities": len(self._entities),
                "threat_assessments": len(self._threat_assessments),
                "snapshots": len(self._snapshots),
            }
            self._entities.clear()
            self._threat_assessments.clear()
            self._snapshots.clear()
            self._last_updated = datetime.now(UTC)
            return counts


_cop_state_instance: COPState | None = None
_instance_lock = Lock()


def get_cop_state(
    mapa_base_url: str = "http://localhost:3000", auto_sync: bool = True, auto_load: bool = False
) -> COPState:
    global _cop_state_instance
    if _cop_state_instance is None:
        with _instance_lock:
            if _cop_state_instance is None:
                _cop_state_instance = COPState(
                    mapa_base_url=mapa_base_url, auto_sync=auto_sync, auto_load=auto_load
                )
    return _cop_state_instance


def reset_cop_state() -> None:
    global _cop_state_instance
    with _instance_lock:
        _cop_state_instance = None
