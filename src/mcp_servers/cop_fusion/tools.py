"""
COP Fusion Tools - Deterministic operations for COP management.
"""

import math
from datetime import UTC, datetime
from typing import Any

from src.core.telemetry import get_tracer, traced_operation
from src.mcp_servers.cop_fusion.state import COPState
from src.models.cop import EntityCOP, Location

tracer = get_tracer("copforge.mcp.cop_fusion.tools")

DEFAULT_DISTANCE_THRESHOLD_M = 500
DEFAULT_TIME_WINDOW_SEC = 300
MULTI_SENSOR_CONFIDENCE_BOOST = 0.1
MAX_CONFIDENCE = 0.99
EARTH_RADIUS_M = 6_371_000


def haversine_distance(loc1: Location, loc2: Location) -> float:
    """Calculate Haversine distance between two locations in meters."""
    lat1, lon1 = math.radians(loc1.lat), math.radians(loc1.lon)
    lat2, lon2 = math.radians(loc2.lat), math.radians(loc2.lon)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return EARTH_RADIUS_M * 2 * math.asin(math.sqrt(a))


def find_duplicates(
    cop_state: COPState,
    entity_data: dict[str, Any],
    distance_threshold_m: float = DEFAULT_DISTANCE_THRESHOLD_M,
    time_window_sec: float = DEFAULT_TIME_WINDOW_SEC,
) -> dict[str, Any]:
    """Find potential duplicate entities in the COP."""
    with traced_operation(
        tracer, "find_duplicates", {"distance_threshold_m": distance_threshold_m}
    ) as span:
        try:
            entity = EntityCOP(**entity_data)
        except Exception as e:
            return {"error": f"Invalid entity data: {e!s}", "matches": []}

        matches: list[dict[str, Any]] = []
        for existing_id, existing in cop_state.entities.items():
            if existing_id == entity.entity_id:
                continue
            if existing.entity_type != entity.entity_type:
                continue
            if existing.classification != entity.classification:
                continue
            distance_m = haversine_distance(entity.location, existing.location)
            if distance_m > distance_threshold_m:
                continue
            time_diff = abs((entity.timestamp - existing.timestamp).total_seconds())
            if time_diff > time_window_sec:
                continue
            spatial_score = 1.0 - (distance_m / distance_threshold_m)
            temporal_score = 1.0 - (time_diff / time_window_sec)
            combined_score = (spatial_score * 0.7) + (temporal_score * 0.3)
            matches.append(
                {
                    "entity_id": existing_id,
                    "entity_type": existing.entity_type,
                    "classification": existing.classification,
                    "distance_m": round(distance_m, 2),
                    "time_diff_sec": round(time_diff, 1),
                    "score": round(combined_score, 3),
                    "existing_sensors": existing.source_sensors,
                }
            )
        matches.sort(key=lambda m: m["score"], reverse=True)
        span.set_attribute("cop.matches_found", len(matches))
        return {
            "matches": matches,
            "query_entity_id": entity.entity_id,
            "thresholds": {"distance_m": distance_threshold_m, "time_window_sec": time_window_sec},
        }


def merge_entities(
    cop_state: COPState, entity1_id: str, entity2_id: str, keep_id: str | None = None
) -> dict[str, Any]:
    """Merge two entities. Uses location from entity with most recent timestamp."""
    with traced_operation(
        tracer, "merge_entities", {"entity1_id": entity1_id, "entity2_id": entity2_id}
    ) as span:
        entity1 = cop_state.get_entity(entity1_id)
        entity2 = cop_state.get_entity(entity2_id)
        if entity1 is None:
            return {"error": f"Entity not found: {entity1_id}"}
        if entity2 is None:
            return {"error": f"Entity not found: {entity2_id}"}

        final_id = keep_id if keep_id in (entity1_id, entity2_id) else entity1_id
        newer = entity1 if entity1.timestamp >= entity2.timestamp else entity2
        older = entity2 if newer == entity1 else entity1

        # USE LOCATION FROM MOST RECENT ENTITY
        merged_location = Location(
            lat=newer.location.lat,
            lon=newer.location.lon,
            alt=newer.location.alt or older.location.alt,
        )
        combined_sensors = list(set(entity1.source_sensors + entity2.source_sensors))
        merged_confidence = min(
            MAX_CONFIDENCE,
            max(entity1.confidence, entity2.confidence) + MULTI_SENSOR_CONFIDENCE_BOOST,
        )
        merged_metadata = {
            **older.metadata,
            **newer.metadata,
            "merged_from": [entity1_id, entity2_id],
            "merge_timestamp": datetime.now(UTC).isoformat(),
        }

        classification_order = [
            "UNCLASSIFIED",
            "RESTRICTED",
            "CONFIDENTIAL",
            "SECRET",
            "TOP_SECRET",
        ]
        merged = EntityCOP(
            entity_id=final_id,
            entity_type=newer.entity_type,
            location=merged_location,
            heading=newer.heading or older.heading,
            speed_kmh=newer.speed_kmh or older.speed_kmh,
            classification=newer.classification,
            information_classification=max(
                entity1.information_classification,
                entity2.information_classification,
                key=lambda x: classification_order.index(x),
            ),
            confidence=merged_confidence,
            timestamp=newer.timestamp,
            source_sensors=combined_sensors,
            metadata=merged_metadata,
            comments=newer.comments or older.comments,
        )

        removed_id = entity2_id if final_id == entity1_id else entity1_id
        cop_state.remove_entity(removed_id)
        cop_state.upsert_entity(merged)
        span.set_attribute("cop.merged_sensors", len(combined_sensors))
        return {
            "merged_entity": merged.model_dump_json_safe(),
            "removed_entity_id": removed_id,
            "kept_entity_id": final_id,
            "sensors_combined": combined_sensors,
            "confidence_after_merge": merged_confidence,
            "location_source": "newer_entity",
            "newer_entity_id": entity1_id if newer == entity1 else entity2_id,
        }


def update_cop(cop_state: COPState, entities_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Add or update entities in the COP."""
    with traced_operation(tracer, "update_cop", {"entities_count": len(entities_data)}) as span:
        added, updated = 0, 0
        errors: list[dict[str, str]] = []
        for entity_data in entities_data:
            try:
                entity = EntityCOP(**entity_data)
                action = cop_state.upsert_entity(entity)
                if action == "added":
                    added += 1
                else:
                    updated += 1
            except Exception as e:
                errors.append(
                    {"entity_id": entity_data.get("entity_id", "unknown"), "error": str(e)}
                )
        span.set_attribute("cop.added", added)
        span.set_attribute("cop.updated", updated)
        return {
            "added": added,
            "updated": updated,
            "errors": errors,
            "total_processed": len(entities_data),
            "total_entities_in_cop": len(cop_state.entities),
        }


def query_cop(
    cop_state: COPState,
    entity_type: str | None = None,
    classification: str | None = None,
    bbox: list[float] | None = None,
    since_timestamp: str | None = None,
    min_confidence: float | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Query entities from the COP with filters."""
    with traced_operation(tracer, "query_cop") as span:
        entities = list(cop_state.entities.values())
        results: list[EntityCOP] = []
        ts_filter: datetime | None = None
        if since_timestamp:
            try:
                ts_filter = datetime.fromisoformat(since_timestamp.replace("Z", "+00:00"))
            except ValueError:
                return {"error": f"Invalid timestamp format: {since_timestamp}"}
        bbox_filter: tuple[float, float, float, float] | None = None
        if bbox:
            if len(bbox) != 4:
                return {"error": "bbox must have 4 values: [min_lat, min_lon, max_lat, max_lon]"}
            bbox_filter = (bbox[0], bbox[1], bbox[2], bbox[3])

        for entity in entities:
            if entity_type and entity.entity_type != entity_type:
                continue
            if classification and entity.classification != classification.lower():
                continue
            if min_confidence and entity.confidence < min_confidence:
                continue
            if ts_filter and entity.timestamp < ts_filter:
                continue
            if bbox_filter:
                min_lat, min_lon, max_lat, max_lon = bbox_filter
                if not (
                    min_lat <= entity.location.lat <= max_lat
                    and min_lon <= entity.location.lon <= max_lon
                ):
                    continue
            results.append(entity)
            if len(results) >= limit:
                break

        span.set_attribute("cop.results_count", len(results))
        return {
            "entities": [e.model_dump_json_safe() for e in results],
            "count": len(results),
            "total_in_cop": len(entities),
            "filters_applied": {
                "entity_type": entity_type,
                "classification": classification,
                "bbox": bbox,
                "since_timestamp": since_timestamp,
                "min_confidence": min_confidence,
                "limit": limit,
            },
        }


def get_cop_stats(cop_state: COPState) -> dict[str, Any]:
    """Get aggregate statistics about the COP."""
    with traced_operation(tracer, "get_cop_stats"):
        return cop_state.get_stats()


def sync_to_mapa(cop_state: COPState) -> dict[str, Any]:
    """Sync all entities to mapa-puntos-interes."""
    with traced_operation(tracer, "sync_to_mapa") as span:
        result = cop_state.sync_all_to_mapa()
        span.set_attribute("sync.success", result.get("success", False))
        return result


def load_from_mapa(cop_state: COPState) -> dict[str, Any]:
    """Load all entities from mapa-puntos-interes into COP cache."""
    with traced_operation(tracer, "load_from_mapa") as span:
        result = cop_state.load_from_mapa()
        span.set_attribute("load.success", result.get("success", False))
        return result


def check_mapa_connection(cop_state: COPState) -> dict[str, Any]:
    """Check connection to mapa-puntos-interes server."""
    with traced_operation(tracer, "check_mapa_connection") as span:
        is_connected, message = cop_state.check_mapa_connection()
        span.set_attribute("mapa.connected", is_connected)
        return {"connected": is_connected, "message": message}
