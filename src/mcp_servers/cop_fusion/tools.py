"""
COP Fusion Tools.

Deterministic operations for COP management:
- find_duplicates: Haversine-based duplicate detection
- merge_entities: Sensor fusion for combining entities
- update_cop: Batch add/update operations
- query_cop: Filtered queries
- get_cop_stats: Aggregate statistics
"""

import math
from datetime import UTC, datetime
from typing import Any

from src.core.telemetry import get_tracer, traced_operation
from src.mcp_servers.cop_fusion.state import COPState
from src.models.cop import EntityCOP, Location

# =============================================================================
# Configuration
# =============================================================================

tracer = get_tracer("copforge.mcp.cop_fusion.tools")

# Thresholds for duplicate detection
DEFAULT_DISTANCE_THRESHOLD_M = 500  # meters
DEFAULT_TIME_WINDOW_SEC = 300  # 5 minutes

# Confidence boost when merging from multiple sensors
MULTI_SENSOR_CONFIDENCE_BOOST = 0.1
MAX_CONFIDENCE = 0.99

# =============================================================================
# Haversine Distance Calculation
# =============================================================================

EARTH_RADIUS_M = 6_371_000  # Earth radius in meters


def haversine_distance(loc1: Location, loc2: Location) -> float:
    """
    Calculate the Haversine distance between two locations.

    Args:
        loc1: First location
        loc2: Second location

    Returns:
        Distance in meters
    """
    lat1, lon1 = math.radians(loc1.lat), math.radians(loc1.lon)
    lat2, lon2 = math.radians(loc2.lat), math.radians(loc2.lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return EARTH_RADIUS_M * c


# =============================================================================
# Tool: find_duplicates
# =============================================================================


def find_duplicates(
    cop_state: COPState,
    entity_data: dict[str, Any],
    distance_threshold_m: float = DEFAULT_DISTANCE_THRESHOLD_M,
    time_window_sec: float = DEFAULT_TIME_WINDOW_SEC,
) -> dict[str, Any]:
    """
    Find potential duplicate entities in the COP.

    Args:
        cop_state: Current COP state
        entity_data: EntityCOP data as dict
        distance_threshold_m: Maximum distance for duplicate detection
        time_window_sec: Maximum time difference for duplicate detection

    Returns:
        Dict with 'matches' list and metadata
    """
    with traced_operation(
        tracer,
        "find_duplicates",
        {
            "distance_threshold_m": distance_threshold_m,
            "time_window_sec": time_window_sec,
        },
    ) as span:
        try:
            # Parse input entity
            entity = EntityCOP(**entity_data)
        except Exception as e:
            return {"error": f"Invalid entity data: {e!s}", "matches": []}

        matches: list[dict[str, Any]] = []
        entities = cop_state.entities

        for existing_id, existing in entities.items():
            # Skip self-comparison
            if existing_id == entity.entity_id:
                continue

            # Skip different entity types (aircraft won't match ship)
            if existing.entity_type != entity.entity_type:
                continue

            # Calculate spatial distance
            distance_m = haversine_distance(entity.location, existing.location)

            # Skip if too far
            if distance_m > distance_threshold_m:
                continue

            # Calculate temporal distance
            time_diff = abs((entity.timestamp - existing.timestamp).total_seconds())

            # Skip if too old
            if time_diff > time_window_sec:
                continue

            # Calculate similarity score (closer = higher score)
            spatial_score = 1.0 - (distance_m / distance_threshold_m)
            temporal_score = 1.0 - (time_diff / time_window_sec)
            combined_score = (spatial_score * 0.7) + (temporal_score * 0.3)

            matches.append(
                {
                    "entity_id": existing_id,
                    "entity_type": existing.entity_type,
                    "distance_m": round(distance_m, 2),
                    "time_diff_sec": round(time_diff, 1),
                    "score": round(combined_score, 3),
                    "existing_sensors": existing.source_sensors,
                }
            )

        # Sort by score (highest first)
        matches.sort(key=lambda m: m["score"], reverse=True)

        span.set_attribute("cop.matches_found", len(matches))
        return {
            "matches": matches,
            "query_entity_id": entity.entity_id,
            "thresholds": {
                "distance_m": distance_threshold_m,
                "time_window_sec": time_window_sec,
            },
        }


# =============================================================================
# Tool: merge_entities
# =============================================================================


def merge_entities(
    cop_state: COPState,
    entity1_id: str,
    entity2_id: str,
    keep_id: str | None = None,
) -> dict[str, Any]:
    """
    Merge two entities into one.

    Args:
        cop_state: Current COP state
        entity1_id: ID of first entity
        entity2_id: ID of second entity
        keep_id: Which ID to keep (default: entity1_id)

    Returns:
        Dict with merged entity data or error
    """
    with traced_operation(
        tracer,
        "merge_entities",
        {"entity1_id": entity1_id, "entity2_id": entity2_id},
    ) as span:
        # Get entities
        entity1 = cop_state.get_entity(entity1_id)
        entity2 = cop_state.get_entity(entity2_id)

        if entity1 is None:
            return {"error": f"Entity not found: {entity1_id}"}
        if entity2 is None:
            return {"error": f"Entity not found: {entity2_id}"}

        # Determine which ID to keep
        final_id = keep_id if keep_id in (entity1_id, entity2_id) else entity1_id

        # Determine which entity is newer
        newer = entity1 if entity1.timestamp >= entity2.timestamp else entity2
        older = entity2 if newer == entity1 else entity1

        # Weighted location average (by confidence)
        total_conf = entity1.confidence + entity2.confidence
        if total_conf > 0:
            w1 = entity1.confidence / total_conf
            w2 = entity2.confidence / total_conf
        else:
            w1 = w2 = 0.5

        merged_lat = (entity1.location.lat * w1) + (entity2.location.lat * w2)
        merged_lon = (entity1.location.lon * w1) + (entity2.location.lon * w2)

        # Altitude: prefer newer, or average if both have it
        merged_alt = None
        if newer.location.alt is not None:
            merged_alt = newer.location.alt
        elif older.location.alt is not None:
            merged_alt = older.location.alt

        # Combine sensors
        combined_sensors = list(set(entity1.source_sensors + entity2.source_sensors))

        # Boost confidence (more sensors = higher confidence)
        merged_confidence = min(
            MAX_CONFIDENCE,
            max(entity1.confidence, entity2.confidence) + MULTI_SENSOR_CONFIDENCE_BOOST,
        )

        # Merge metadata
        merged_metadata = {**older.metadata, **newer.metadata}
        merged_metadata["merged_from"] = [entity1_id, entity2_id]
        merged_metadata["merge_timestamp"] = datetime.now(UTC).isoformat()

        # Create merged entity
        merged = EntityCOP(
            entity_id=final_id,
            entity_type=newer.entity_type,
            location=Location(lat=merged_lat, lon=merged_lon, alt=merged_alt),
            heading=newer.heading if newer.heading is not None else older.heading,
            speed_kmh=newer.speed_kmh if newer.speed_kmh is not None else older.speed_kmh,
            classification=newer.classification,
            information_classification=max(
                entity1.information_classification,
                entity2.information_classification,
                key=lambda x: [
                    "UNCLASSIFIED",
                    "RESTRICTED",
                    "CONFIDENTIAL",
                    "SECRET",
                    "TOP_SECRET",
                ].index(x),
            ),
            confidence=merged_confidence,
            timestamp=newer.timestamp,
            source_sensors=combined_sensors,
            metadata=merged_metadata,
            comments=newer.comments or older.comments,
        )

        # Update COP: remove old entities, add merged
        removed_id = entity2_id if final_id == entity1_id else entity1_id
        cop_state.remove_entity(removed_id)
        cop_state.upsert_entity(merged)

        span.set_attribute("cop.merged_sensors", len(combined_sensors))
        span.set_attribute("cop.merged_confidence", merged_confidence)

        return {
            "merged_entity": merged.model_dump_json_safe(),
            "removed_entity_id": removed_id,
            "kept_entity_id": final_id,
            "sensors_combined": combined_sensors,
            "confidence_after_merge": merged_confidence,
        }


# =============================================================================
# Tool: update_cop
# =============================================================================


def update_cop(
    cop_state: COPState,
    entities_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Add or update entities in the COP.

    Args:
        cop_state: Current COP state
        entities_data: List of EntityCOP data dicts

    Returns:
        Statistics about the operation
    """
    with traced_operation(
        tracer,
        "update_cop",
        {"entities_count": len(entities_data)},
    ) as span:
        added = 0
        updated = 0
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
                entity_id = entity_data.get("entity_id", "unknown")
                errors.append({"entity_id": entity_id, "error": str(e)})

        span.set_attribute("cop.added", added)
        span.set_attribute("cop.updated", updated)
        span.set_attribute("cop.errors", len(errors))

        return {
            "added": added,
            "updated": updated,
            "errors": errors,
            "total_processed": len(entities_data),
            "total_entities_in_cop": len(cop_state.entities),
        }


# =============================================================================
# Tool: query_cop
# =============================================================================


def query_cop(
    cop_state: COPState,
    entity_type: str | None = None,
    classification: str | None = None,
    bbox: list[float] | None = None,
    since_timestamp: str | None = None,
    min_confidence: float | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Query entities from the COP with filters.

    Args:
        cop_state: Current COP state
        entity_type: Filter by type
        classification: Filter by IFF classification
        bbox: Bounding box [min_lat, min_lon, max_lat, max_lon]
        since_timestamp: ISO timestamp for time filter
        min_confidence: Minimum confidence threshold
        limit: Maximum results

    Returns:
        Dict with 'entities' list and query metadata
    """
    with traced_operation(tracer, "query_cop") as span:
        entities = list(cop_state.entities.values())
        results: list[EntityCOP] = []

        # Parse timestamp filter
        ts_filter: datetime | None = None
        if since_timestamp:
            try:
                ts_filter = datetime.fromisoformat(since_timestamp.replace("Z", "+00:00"))
            except ValueError:
                return {"error": f"Invalid timestamp format: {since_timestamp}"}

        # Parse bbox
        bbox_filter: tuple[float, float, float, float] | None = None
        if bbox:
            if len(bbox) != 4:
                return {"error": "bbox must have 4 values: [min_lat, min_lon, max_lat, max_lon]"}
            bbox_filter = (bbox[0], bbox[1], bbox[2], bbox[3])

        for entity in entities:
            # Apply filters
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
                if not (min_lat <= entity.location.lat <= max_lat):
                    continue
                if not (min_lon <= entity.location.lon <= max_lon):
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


# =============================================================================
# Tool: get_cop_stats
# =============================================================================


def get_cop_stats(cop_state: COPState) -> dict[str, Any]:
    """
    Get aggregate statistics about the COP.

    Args:
        cop_state: Current COP state

    Returns:
        Dict with COP statistics
    """
    with traced_operation(tracer, "get_cop_stats"):
        return cop_state.get_stats()
