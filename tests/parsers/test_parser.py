"""
Tests for CopForge parsers.
"""

from datetime import UTC, datetime

import pytest

from src.models.sensor import SensorMessage
from src.parsers import (
    ASTERIXParser,
    DroneParser,
    ManualParser,
    RadioParser,
    get_parser_factory,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def asterix_message() -> SensorMessage:
    """Create a valid ASTERIX radar message."""
    return SensorMessage(
        sensor_id="radar_01",
        sensor_type="radar",
        timestamp=datetime.now(UTC),
        data={
            "format": "asterix",
            "system_id": "ES_RAD_101",
            "is_simulated": False,
            "tracks": [
                {
                    "track_id": "T001",
                    "location": {"lat": 39.5, "lon": -0.4},
                    "altitude_m": 5000,
                    "speed_kmh": 450,
                    "heading": 270,
                    "classification": "unknown",
                    "quality": {
                        "accuracy_m": 50,
                        "plot_count": 5,
                        "ssr_code": "7700",
                    },
                },
                {
                    "track_id": "T002",
                    "location": {"lat": 39.6, "lon": -0.5},
                    "altitude_m": 3000,
                    "speed_kmh": 300,
                    "heading": 180,
                },
            ],
        },
    )


@pytest.fixture
def drone_message() -> SensorMessage:
    """Create a valid drone telemetry message."""
    return SensorMessage(
        sensor_id="drone_alpha",
        sensor_type="drone",
        timestamp=datetime.now(UTC),
        data={
            "drone_id": "DRONE_ALPHA_01",
            "flight_mode": "auto",
            "latitude": 39.4762,
            "longitude": -0.3747,
            "altitude_m_agl": 120,
            "altitude_m_msl": 145,
            "heading": 90,
            "ground_speed_kmh": 45,
            "battery_percent": 78,
            "camera_heading": 90,
            "image_link": "data/drone_alpha/IMG_001.jpg",
        },
    )


@pytest.fixture
def radio_message() -> SensorMessage:
    """Create a valid radio intercept message."""
    return SensorMessage(
        sensor_id="radio_bravo",
        sensor_type="radio",
        timestamp=datetime.now(UTC),
        data={
            "station_id": "INTERCEPT_BRAVO_01",
            "frequency_mhz": 145.500,
            "bandwidth_khz": 12.5,
            "modulation_type": "FM",
            "channel": "tactical_01",
            "duration_sec": 45,
            "signal_strength": -72,
            "audio_path": "data/radio_bravo/transmission_143200.mp3",
            "location": {"lat": 39.5, "lon": -0.4},
        },
    )


@pytest.fixture
def manual_message() -> SensorMessage:
    """Create a valid manual report message."""
    return SensorMessage(
        sensor_id="operator_charlie",
        sensor_type="manual",
        timestamp=datetime.now(UTC),
        data={
            "report_id": "SPOTREP_001",
            "report_type": "SPOTREP",
            "priority": "high",
            "operator_name": "Cpt. Smith",
            "content": "Visual confirmation: Single military aircraft, no IFF response",
            "latitude": 39.50,
            "longitude": -0.35,
        },
    )


# =============================================================================
# ASTERIX Parser Tests
# =============================================================================


class TestASTERIXParser:
    """Tests for ASTERIX radar parser."""

    def test_can_parse_asterix(self, asterix_message: SensorMessage) -> None:
        """Parser should recognize ASTERIX format."""
        parser = ASTERIXParser()
        assert parser.can_parse(asterix_message) is True

    def test_cannot_parse_non_radar(self, drone_message: SensorMessage) -> None:
        """Parser should not recognize non-radar messages."""
        parser = ASTERIXParser()
        assert parser.can_parse(drone_message) is False

    def test_parse_creates_entities(self, asterix_message: SensorMessage) -> None:
        """Parse should create EntityCOP for each track."""
        parser = ASTERIXParser()
        entities = parser.parse(asterix_message)

        assert len(entities) == 2
        entity1 = entities[0]
        assert entity1.entity_id == "radar_01_T001"
        assert entity1.entity_type == "aircraft"
        assert entity1.location.lat == 39.5


# =============================================================================
# Drone Parser Tests
# =============================================================================


class TestDroneParser:
    """Tests for drone telemetry parser."""

    def test_can_parse_drone(self, drone_message: SensorMessage) -> None:
        """Parser should recognize drone format."""
        parser = DroneParser()
        assert parser.can_parse(drone_message) is True

    def test_parse_creates_uav_entity(self, drone_message: SensorMessage) -> None:
        """Parse should create UAV entity."""
        parser = DroneParser()
        entities = parser.parse(drone_message)

        assert len(entities) == 1
        entity = entities[0]
        assert entity.entity_type == "uav"
        assert entity.classification == "friendly"


# =============================================================================
# Radio Parser Tests
# =============================================================================


class TestRadioParser:
    """Tests for radio intercept parser."""

    def test_can_parse_radio(self, radio_message: SensorMessage) -> None:
        """Parser should recognize radio format."""
        parser = RadioParser()
        assert parser.can_parse(radio_message) is True

    def test_parse_creates_event_entity(self, radio_message: SensorMessage) -> None:
        """Parse should create event entity for intercept."""
        parser = RadioParser()
        entities = parser.parse(radio_message)

        assert len(entities) == 1
        entity = entities[0]
        assert entity.entity_type == "event"


# =============================================================================
# Manual Parser Tests
# =============================================================================


class TestManualParser:
    """Tests for manual report parser."""

    def test_can_parse_manual(self, manual_message: SensorMessage) -> None:
        """Parser should recognize manual format."""
        parser = ManualParser()
        assert parser.can_parse(manual_message) is True

    def test_parse_creates_event_entity(self, manual_message: SensorMessage) -> None:
        """Parse should create event entity for report."""
        parser = ManualParser()
        entities = parser.parse(manual_message)

        assert len(entities) == 1
        entity = entities[0]
        assert entity.entity_type == "event"


# =============================================================================
# Parser Factory Tests
# =============================================================================


class TestParserFactory:
    """Tests for parser factory."""

    def test_parse_asterix_success(self, asterix_message: SensorMessage) -> None:
        """Factory parse should succeed for valid ASTERIX message."""
        factory = get_parser_factory()
        result = factory.parse(asterix_message)

        assert result.success is True
        assert len(result.entities) == 2
        assert result.parser_used == "ASTERIXParser"

    def test_list_parsers(self) -> None:
        """Factory should list all registered parsers."""
        factory = get_parser_factory()
        parser_names = factory.list_parsers()

        assert "ASTERIXParser" in parser_names
        assert "DroneParser" in parser_names
