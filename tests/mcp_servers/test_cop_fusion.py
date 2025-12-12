"""
Tests for MCP Server: COP Fusion
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.mcp_servers.cop_fusion import (
    COPState,
    find_duplicates,
    get_cop_stats,
    haversine_distance,
    merge_entities,
    query_cop,
    reset_cop_state,
    update_cop,
)
from src.models.cop import EntityCOP, Location

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def cop_state() -> COPState:
    """Create a fresh COP state for each test."""
    reset_cop_state()
    return COPState()


@pytest.fixture
def sample_aircraft() -> EntityCOP:
    """Create a sample aircraft entity."""
    return EntityCOP(
        entity_id="aircraft_001",
        entity_type="aircraft",
        location=Location(lat=39.5, lon=-0.4, alt=5000),
        heading=270,
        speed_kmh=450,
        classification="unknown",
        information_classification="SECRET",
        confidence=0.8,
        timestamp=datetime.now(UTC),
        source_sensors=["radar_01"],
    )


@pytest.fixture
def sample_aircraft_nearby() -> EntityCOP:
    """Create a nearby aircraft (potential duplicate)."""
    return EntityCOP(
        entity_id="aircraft_002",
        entity_type="aircraft",
        location=Location(lat=39.501, lon=-0.401, alt=5100),  # ~150m away
        heading=272,
        speed_kmh=448,
        classification="unknown",
        information_classification="SECRET",
        confidence=0.75,
        timestamp=datetime.now(UTC) - timedelta(seconds=30),
        source_sensors=["radar_02"],
    )


@pytest.fixture
def sample_ship() -> EntityCOP:
    """Create a sample ship entity."""
    return EntityCOP(
        entity_id="ship_001",
        entity_type="ship",
        location=Location(lat=39.0, lon=-0.1),
        heading=90,
        speed_kmh=30,
        classification="friendly",
        information_classification="CONFIDENTIAL",
        confidence=0.9,
        timestamp=datetime.now(UTC),
        source_sensors=["ais_01"],
    )


@pytest.fixture
def populated_cop(
    cop_state: COPState, sample_aircraft: EntityCOP, sample_ship: EntityCOP
) -> COPState:
    """Create a COP with some entities already present."""
    cop_state.add_entity(sample_aircraft)
    cop_state.add_entity(sample_ship)
    return cop_state


# =============================================================================
# Haversine Distance Tests
# =============================================================================


class TestHaversineDistance:
    """Tests for Haversine distance calculation."""

    def test_same_point_zero_distance(self) -> None:
        """Same point should have zero distance."""
        loc = Location(lat=39.5, lon=-0.4)
        assert haversine_distance(loc, loc) == 0.0

    def test_known_distance(self) -> None:
        """Test against known distance (Valencia to Madrid ~302km)."""
        valencia = Location(lat=39.4699, lon=-0.3763)
        madrid = Location(lat=40.4168, lon=-3.7038)

        distance = haversine_distance(valencia, madrid)

        # Should be approximately 302km
        assert 295_000 < distance < 310_000

    def test_short_distance(self) -> None:
        """Test short distance calculation."""
        loc1 = Location(lat=39.5, lon=-0.4)
        loc2 = Location(lat=39.501, lon=-0.401)  # ~150m away

        distance = haversine_distance(loc1, loc2)

        # Should be approximately 150m
        assert 100 < distance < 200


# =============================================================================
# COPState Tests
# =============================================================================


class TestCOPState:
    """Tests for COP state management."""

    def test_add_entity(self, cop_state: COPState, sample_aircraft: EntityCOP) -> None:
        """Should add entity to COP."""
        result = cop_state.add_entity(sample_aircraft)

        assert result is True
        assert sample_aircraft.entity_id in cop_state.entities

    def test_add_duplicate_fails(self, cop_state: COPState, sample_aircraft: EntityCOP) -> None:
        """Adding duplicate entity_id should fail."""
        cop_state.add_entity(sample_aircraft)
        result = cop_state.add_entity(sample_aircraft)

        assert result is False

    def test_update_entity(self, cop_state: COPState, sample_aircraft: EntityCOP) -> None:
        """Should update existing entity."""
        cop_state.add_entity(sample_aircraft)

        # Modify and update
        sample_aircraft.confidence = 0.95
        result = cop_state.update_entity(sample_aircraft)

        assert result is True
        assert cop_state.get_entity(sample_aircraft.entity_id).confidence == 0.95

    def test_update_nonexistent_fails(
        self, cop_state: COPState, sample_aircraft: EntityCOP
    ) -> None:
        """Updating nonexistent entity should fail."""
        result = cop_state.update_entity(sample_aircraft)
        assert result is False

    def test_upsert_adds_new(self, cop_state: COPState, sample_aircraft: EntityCOP) -> None:
        """Upsert should add new entity."""
        result = cop_state.upsert_entity(sample_aircraft)

        assert result == "added"
        assert sample_aircraft.entity_id in cop_state.entities

    def test_upsert_updates_existing(self, cop_state: COPState, sample_aircraft: EntityCOP) -> None:
        """Upsert should update existing entity."""
        cop_state.add_entity(sample_aircraft)

        sample_aircraft.confidence = 0.95
        result = cop_state.upsert_entity(sample_aircraft)

        assert result == "updated"

    def test_remove_entity(self, cop_state: COPState, sample_aircraft: EntityCOP) -> None:
        """Should remove entity from COP."""
        cop_state.add_entity(sample_aircraft)
        result = cop_state.remove_entity(sample_aircraft.entity_id)

        assert result is True
        assert sample_aircraft.entity_id not in cop_state.entities

    def test_create_snapshot(self, populated_cop: COPState) -> None:
        """Should create snapshot of current state."""
        snapshot = populated_cop.create_snapshot()

        assert snapshot.snapshot_id is not None
        assert len(snapshot.entities) == 2

    def test_get_stats(self, populated_cop: COPState) -> None:
        """Should return correct statistics."""
        stats = populated_cop.get_stats()

        assert stats["total_entities"] == 2
        assert stats["by_type"]["aircraft"] == 1
        assert stats["by_type"]["ship"] == 1


# =============================================================================
# find_duplicates Tool Tests
# =============================================================================


class TestFindDuplicates:
    """Tests for find_duplicates tool."""

    def test_finds_nearby_duplicate(
        self,
        populated_cop: COPState,
        sample_aircraft_nearby: EntityCOP,
    ) -> None:
        """Should find nearby entity as potential duplicate."""
        result = find_duplicates(
            cop_state=populated_cop,
            entity_data=sample_aircraft_nearby.model_dump_json_safe(),
            distance_threshold_m=500,
            time_window_sec=300,
        )

        assert len(result["matches"]) == 1
        assert result["matches"][0]["entity_id"] == "aircraft_001"
        assert result["matches"][0]["distance_m"] < 200

    def test_no_duplicates_for_different_type(
        self,
        populated_cop: COPState,
        _sample_ship: EntityCOP,
    ) -> None:
        """Should not match entities of different types."""
        # Create ship-like entity near aircraft
        ship_near_aircraft = EntityCOP(
            entity_id="ship_002",
            entity_type="ship",
            location=Location(lat=39.501, lon=-0.401),  # Near aircraft
            timestamp=datetime.now(UTC),
            source_sensors=["ais_02"],
        )

        result = find_duplicates(
            cop_state=populated_cop,
            entity_data=ship_near_aircraft.model_dump_json_safe(),
        )

        # Should only match ship_001, not aircraft_001
        match_ids = [m["entity_id"] for m in result["matches"]]
        assert "aircraft_001" not in match_ids

    def test_no_duplicates_when_too_far(self, populated_cop: COPState) -> None:
        """Should not find duplicates when entity is too far."""
        far_aircraft = EntityCOP(
            entity_id="aircraft_far",
            entity_type="aircraft",
            location=Location(lat=40.0, lon=-1.0),  # ~100km away
            timestamp=datetime.now(UTC),
            source_sensors=["radar_03"],
        )

        result = find_duplicates(
            cop_state=populated_cop,
            entity_data=far_aircraft.model_dump_json_safe(),
        )

        assert len(result["matches"]) == 0

    def test_no_duplicates_when_too_old(self, populated_cop: COPState) -> None:
        """Should not find duplicates when time difference is too large."""
        old_aircraft = EntityCOP(
            entity_id="aircraft_old",
            entity_type="aircraft",
            location=Location(lat=39.501, lon=-0.401),  # Near existing
            timestamp=datetime.now(UTC) - timedelta(hours=1),  # Old
            source_sensors=["radar_03"],
        )

        result = find_duplicates(
            cop_state=populated_cop,
            entity_data=old_aircraft.model_dump_json_safe(),
            time_window_sec=300,
        )

        assert len(result["matches"]) == 0


# =============================================================================
# merge_entities Tool Tests
# =============================================================================


class TestMergeEntities:
    """Tests for merge_entities tool."""

    def test_merge_combines_sensors(
        self,
        cop_state: COPState,
        sample_aircraft: EntityCOP,
        sample_aircraft_nearby: EntityCOP,
    ) -> None:
        """Merged entity should have combined sensor list."""
        cop_state.add_entity(sample_aircraft)
        cop_state.add_entity(sample_aircraft_nearby)

        result = merge_entities(
            cop_state=cop_state,
            entity1_id=sample_aircraft.entity_id,
            entity2_id=sample_aircraft_nearby.entity_id,
        )

        assert "error" not in result
        assert "radar_01" in result["sensors_combined"]
        assert "radar_02" in result["sensors_combined"]

    def test_merge_uses_newer_location(
        self,
        cop_state: COPState,
    ) -> None:
        """Merged entity should use location from entity with most recent timestamp."""
        from datetime import timedelta

        # Create two aircraft at different locations and times
        older_aircraft = EntityCOP(
            entity_id="aircraft_old",
            entity_type="aircraft",
            location=Location(lat=39.0, lon=-0.5, alt=5000),
            timestamp=datetime.now(UTC) - timedelta(minutes=5),
            confidence=0.8,
            source_sensors=["radar_01"],
        )
        newer_aircraft = EntityCOP(
            entity_id="aircraft_new",
            entity_type="aircraft",
            location=Location(lat=40.0, lon=-1.0, alt=6000),
            timestamp=datetime.now(UTC),
            confidence=0.75,
            source_sensors=["radar_02"],
        )

        cop_state.add_entity(older_aircraft)
        cop_state.add_entity(newer_aircraft)

        result = merge_entities(
            cop_state=cop_state,
            entity1_id=older_aircraft.entity_id,
            entity2_id=newer_aircraft.entity_id,
        )

        assert "error" not in result
        # Merged entity should use newer location
        merged = result["merged_entity"]
        assert merged["location"]["lat"] == 40.0
        assert merged["location"]["lon"] == -1.0
        assert result["newer_entity_id"] == "aircraft_new"

    def test_merge_removes_duplicate(
        self,
        cop_state: COPState,
        sample_aircraft: EntityCOP,
        sample_aircraft_nearby: EntityCOP,
    ) -> None:
        """Merge should remove the duplicate entity from COP."""
        cop_state.add_entity(sample_aircraft)
        cop_state.add_entity(sample_aircraft_nearby)

        result = merge_entities(
            cop_state=cop_state,
            entity1_id=sample_aircraft.entity_id,
            entity2_id=sample_aircraft_nearby.entity_id,
        )

        # Should now have only one entity
        assert len(cop_state.entities) == 1
        assert result["removed_entity_id"] not in cop_state.entities

    def test_merge_nonexistent_fails(self, cop_state: COPState, sample_aircraft: EntityCOP) -> None:
        """Merging with nonexistent entity should fail."""
        cop_state.add_entity(sample_aircraft)

        result = merge_entities(
            cop_state=cop_state,
            entity1_id=sample_aircraft.entity_id,
            entity2_id="nonexistent",
        )

        assert "error" in result


# =============================================================================
# update_cop Tool Tests
# =============================================================================


class TestUpdateCOP:
    """Tests for update_cop tool."""

    def test_add_multiple_entities(self, cop_state: COPState) -> None:
        """Should add multiple entities at once."""
        entities_data = [
            {
                "entity_id": "test_001",
                "entity_type": "aircraft",
                "location": {"lat": 39.5, "lon": -0.4},
                "timestamp": datetime.now(UTC).isoformat(),
                "source_sensors": ["radar_01"],
            },
            {
                "entity_id": "test_002",
                "entity_type": "ship",
                "location": {"lat": 39.0, "lon": -0.1},
                "timestamp": datetime.now(UTC).isoformat(),
                "source_sensors": ["ais_01"],
            },
        ]

        result = update_cop(cop_state=cop_state, entities_data=entities_data)

        assert result["added"] == 2
        assert result["updated"] == 0
        assert result["total_entities_in_cop"] == 2

    def test_update_existing_entity(
        self,
        populated_cop: COPState,
        sample_aircraft: EntityCOP,
    ) -> None:
        """Should update existing entity."""
        updated_data = sample_aircraft.model_dump_json_safe()
        updated_data["confidence"] = 0.95

        result = update_cop(cop_state=populated_cop, entities_data=[updated_data])

        assert result["added"] == 0
        assert result["updated"] == 1

    def test_handles_invalid_data(self, cop_state: COPState) -> None:
        """Should handle invalid entity data gracefully."""
        entities_data = [
            {
                "entity_id": "valid",
                "entity_type": "aircraft",
                "location": {"lat": 39.5, "lon": -0.4},
            },
            {"invalid": "data"},  # Missing required fields
        ]

        result = update_cop(cop_state=cop_state, entities_data=entities_data)

        assert result["added"] == 1
        assert len(result["errors"]) == 1


# =============================================================================
# query_cop Tool Tests
# =============================================================================


class TestQueryCOP:
    """Tests for query_cop tool."""

    def test_query_all(self, populated_cop: COPState) -> None:
        """Query without filters should return all entities."""
        result = query_cop(cop_state=populated_cop)

        assert result["count"] == 2

    def test_query_by_type(self, populated_cop: COPState) -> None:
        """Should filter by entity type."""
        result = query_cop(cop_state=populated_cop, entity_type="aircraft")

        assert result["count"] == 1
        assert result["entities"][0]["entity_type"] == "aircraft"

    def test_query_by_classification(self, populated_cop: COPState) -> None:
        """Should filter by classification."""
        result = query_cop(cop_state=populated_cop, classification="friendly")

        assert result["count"] == 1
        assert result["entities"][0]["classification"] == "friendly"

    def test_query_by_bbox(self, populated_cop: COPState) -> None:
        """Should filter by bounding box."""
        # Bbox around aircraft location only
        result = query_cop(
            cop_state=populated_cop,
            bbox=[39.4, -0.5, 39.6, -0.3],
        )

        assert result["count"] == 1
        assert result["entities"][0]["entity_id"] == "aircraft_001"

    def test_query_by_min_confidence(self, populated_cop: COPState) -> None:
        """Should filter by minimum confidence."""
        result = query_cop(cop_state=populated_cop, min_confidence=0.85)

        assert result["count"] == 1
        assert result["entities"][0]["confidence"] >= 0.85

    def test_query_with_limit(self, populated_cop: COPState) -> None:
        """Should respect limit parameter."""
        result = query_cop(cop_state=populated_cop, limit=1)

        assert result["count"] == 1


# =============================================================================
# get_cop_stats Tool Tests
# =============================================================================


class TestGetCOPStats:
    """Tests for get_cop_stats tool."""

    def test_empty_cop_stats(self, cop_state: COPState) -> None:
        """Empty COP should return zero counts."""
        stats = get_cop_stats(cop_state)

        assert stats["total_entities"] == 0
        assert stats["unique_sensors"] == 0

    def test_populated_cop_stats(self, populated_cop: COPState) -> None:
        """Populated COP should return correct stats."""
        stats = get_cop_stats(populated_cop)

        assert stats["total_entities"] == 2
        assert stats["by_type"]["aircraft"] == 1
        assert stats["by_type"]["ship"] == 1
        assert stats["by_classification"]["unknown"] == 1
        assert stats["by_classification"]["friendly"] == 1
        assert stats["unique_sensors"] == 2
