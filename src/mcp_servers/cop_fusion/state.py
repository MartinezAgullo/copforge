"""
COP State Management.

In-memory state store for the Common Operational Picture.
Can be extended to use persistent storage (PostgreSQL, Redis).
"""

from datetime import UTC, datetime
from threading import Lock
from typing import Any

from src.core.telemetry import get_tracer, traced_operation
from src.models.cop import COPSnapshot, EntityCOP, ThreatAssessment

# =============================================================================
# Configuration
# =============================================================================

tracer = get_tracer("copforge.mcp.cop_fusion.state")

# =============================================================================
# COP State Class
# =============================================================================


class COPState:
    """
    Thread-safe in-memory state for the Common Operational Picture.

    Attributes:
        entities: Dictionary mapping entity_id -> EntityCOP
        threat_assessments: List of active threat assessments
        snapshots: Historical snapshots for audit/recovery
    """

    def __init__(self) -> None:
        """Initialize empty COP state."""
        self._lock = Lock()
        self._entities: dict[str, EntityCOP] = {}
        self._threat_assessments: list[ThreatAssessment] = []
        self._snapshots: list[COPSnapshot] = []
        self._created_at = datetime.now(UTC)
        self._last_updated = self._created_at

    @property
    def entities(self) -> dict[str, EntityCOP]:
        """Get a copy of entities dict (thread-safe read)."""
        with self._lock:
            return self._entities.copy()

    @property
    def threat_assessments(self) -> list[ThreatAssessment]:
        """Get a copy of threat assessments (thread-safe read)."""
        with self._lock:
            return self._threat_assessments.copy()

    def get_entity(self, entity_id: str) -> EntityCOP | None:
        """Get a specific entity by ID."""
        with self._lock:
            return self._entities.get(entity_id)

    def add_entity(self, entity: EntityCOP) -> bool:
        """
        Add a new entity to the COP.

        Returns True if added, False if entity_id already exists.
        """
        with traced_operation(tracer, "add_entity", {"entity_id": entity.entity_id}), self._lock:
            if entity.entity_id in self._entities:
                return False
            self._entities[entity.entity_id] = entity
            self._last_updated = datetime.now(UTC)
            return True

    def update_entity(self, entity: EntityCOP) -> bool:
        """
        Update an existing entity in the COP.

        Returns True if updated, False if entity_id doesn't exist.
        """
        with traced_operation(tracer, "update_entity", {"entity_id": entity.entity_id}), self._lock:
            if entity.entity_id not in self._entities:
                return False
            self._entities[entity.entity_id] = entity
            self._last_updated = datetime.now(UTC)
            return True

    def upsert_entity(self, entity: EntityCOP) -> str:
        """
        Add or update an entity.

        Returns 'added' or 'updated'.
        """
        with (
            traced_operation(tracer, "upsert_entity", {"entity_id": entity.entity_id}) as span,
            self._lock,
        ):
            action = "updated" if entity.entity_id in self._entities else "added"
            self._entities[entity.entity_id] = entity
            self._last_updated = datetime.now(UTC)
            span.set_attribute("cop.action", action)
            return action

    def remove_entity(self, entity_id: str) -> bool:
        """
        Remove an entity from the COP.

        Returns True if removed, False if not found.
        """
        with traced_operation(tracer, "remove_entity", {"entity_id": entity_id}), self._lock:
            if entity_id in self._entities:
                del self._entities[entity_id]
                self._last_updated = datetime.now(UTC)
                return True
            return False

    def add_threat_assessment(self, assessment: ThreatAssessment) -> None:
        """Add a threat assessment to the COP."""
        with self._lock:
            self._threat_assessments.append(assessment)
            self._last_updated = datetime.now(UTC)

    def clear_threat_assessments(self) -> int:
        """Clear all threat assessments. Returns count cleared."""
        with self._lock:
            count = len(self._threat_assessments)
            self._threat_assessments.clear()
            return count

    def create_snapshot(self, snapshot_id: str | None = None) -> COPSnapshot:
        """
        Create a snapshot of the current COP state.

        Args:
            snapshot_id: Optional custom ID, otherwise auto-generated.

        Returns:
            COPSnapshot containing current state.
        """
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
                    "threat_count": len(self._threat_assessments),
                },
            )

            self._snapshots.append(snapshot)
            return snapshot

    def restore_snapshot(self, snapshot: COPSnapshot) -> None:
        """Restore COP state from a snapshot."""
        with (
            traced_operation(tracer, "restore_snapshot", {"snapshot_id": snapshot.snapshot_id}),
            self._lock,
        ):
            self._entities = snapshot.entities.copy()
            self._threat_assessments = snapshot.threat_assessments.copy()
            self._last_updated = datetime.now(UTC)

    def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics about the COP."""
        with self._lock:
            entities = list(self._entities.values())

            # Count by type
            by_type: dict[str, int] = {}
            for e in entities:
                by_type[e.entity_type] = by_type.get(e.entity_type, 0) + 1

            # Count by classification
            by_classification: dict[str, int] = {}
            for e in entities:
                by_classification[e.classification] = by_classification.get(e.classification, 0) + 1

            # Unique sensors
            sensors: set[str] = set()
            for e in entities:
                sensors.update(e.source_sensors)

            # Average confidence
            avg_confidence = (
                sum(e.confidence for e in entities) / len(entities) if entities else 0.0
            )

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
            }

    def clear(self) -> dict[str, int]:
        """Clear all state. Returns counts of cleared items."""
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


# =============================================================================
# Singleton Instance
# =============================================================================

_cop_state_instance: COPState | None = None
_instance_lock = Lock()


def get_cop_state() -> COPState:
    """
    Get the singleton COP state instance.

    Thread-safe lazy initialization.
    """
    global _cop_state_instance

    if _cop_state_instance is None:
        with _instance_lock:
            if _cop_state_instance is None:
                _cop_state_instance = COPState()

    return _cop_state_instance


def reset_cop_state() -> None:
    """Reset the singleton instance (for testing)."""
    global _cop_state_instance

    with _instance_lock:
        _cop_state_instance = None
