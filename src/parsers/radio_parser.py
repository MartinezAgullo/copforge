"""
Radio Parser for CopForge.

Parser for radio intercept and communications intelligence.
"""

from typing import Any

from src.core.telemetry import get_tracer, traced_operation
from src.models.cop import EntityCOP, Location
from src.models.sensor import SensorMessage
from src.parsers.base_parser import BaseParser

# Get tracer for this module
tracer = get_tracer("copforge.parsers.radio")


class RadioParser(BaseParser):
    """
    Parser for radio intercept data.

    Handles radio communications metadata and COMINT (communications intelligence).
    Does not create entities directly from audio - audio transcription is handled
    by multimodal tools. This parser creates metadata entities for the intercept
    event itself.

    Expected data format:
        {
            "station_id": "INTERCEPT_BRAVO_01",
            "frequency_mhz": 145.500,
            "bandwidth_khz": 12.5,
            "modulation_type": "FM",
            "channel": "tactical_01",
            "duration_sec": 45,
            "signal_strength": -72,
            "audio_path": "data/radio_bravo/transmission_143200.mp3",
            "location": {"lat": 39.5, "lon": -0.4}  # Optional: intercept station location
        }
    """

    def can_parse(self, sensor_msg: SensorMessage) -> bool:
        """Check if message is radio format."""
        if sensor_msg.sensor_type != "radio":
            return False

        data = sensor_msg.data

        # Radio data must have station_id and frequency
        return isinstance(data, dict) and "station_id" in data and "frequency_mhz" in data

    def validate(self, sensor_msg: SensorMessage) -> tuple[bool, str]:
        """Validate radio message structure."""
        data = sensor_msg.data

        if not isinstance(data, dict):
            return False, "Data must be a dictionary"

        # Check required fields
        required = ["station_id", "frequency_mhz", "channel"]
        missing = [field for field in required if field not in data]
        if missing:
            return False, f"Missing required fields: {missing}"

        return True, ""

    def parse(self, sensor_msg: SensorMessage) -> list[EntityCOP]:
        """
        Parse radio intercept data.

        Creates an "event" entity representing the intercept.
        Actual transcription and entity extraction from audio is handled
        by multimodal tools.
        """
        with traced_operation(
            tracer,
            "parse_radio",
            {"sensor_id": sensor_msg.sensor_id},
        ) as span:
            data: dict[str, Any] = sensor_msg.data  # type: ignore
            entities: list[EntityCOP] = []

            # Radio intercept station location (if available)
            # If not provided, we can't create a geographic entity
            if "location" not in data:
                span.set_attribute("skipped", True)
                span.set_attribute("skip_reason", "no_location")
                # No location - skip entity creation
                # Audio transcription will still happen in multimodal processing
                return entities

            loc_data = data["location"]
            location = Location(
                lat=loc_data.get("lat", 0),
                lon=loc_data.get("lon", 0),
                alt=loc_data.get("alt"),
            )

            # Create event entity for the intercept
            station_id = data["station_id"]
            entity_id = f"{sensor_msg.sensor_id}_{station_id}_intercept"

            # Metadata
            metadata: dict[str, Any] = {
                "station_id": station_id,
                "frequency_mhz": data["frequency_mhz"],
                "bandwidth_khz": data.get("bandwidth_khz"),
                "modulation_type": data.get("modulation_type"),
                "channel": data["channel"],
                "duration_sec": data.get("duration_sec"),
                "signal_strength": data.get("signal_strength"),
                "audio_path": data.get("audio_path"),
                "sensor_type": "radio",
            }

            # Check if there's an audio file
            has_audio = bool(data.get("audio_path"))
            if has_audio:
                span.set_attribute("has_audio", True)

            # Radio intercepts are typically SECRET or higher
            # Especially if intercepting adversary communications
            info_classification = data.get("classification_level", "SECRET")

            # Create event entity
            intercept_entity = self._create_entity(
                entity_id=entity_id,
                entity_type="event",  # This is an intercept event
                location=location,
                timestamp=sensor_msg.timestamp,
                sensor_msg=sensor_msg,
                classification="unknown",  # We don't know who transmitted
                information_classification=info_classification,
                confidence=0.7,  # Moderate confidence until transcription confirms
                metadata=metadata,
                comments=f"Radio intercept on {data['frequency_mhz']} MHz",
            )

            entities.append(intercept_entity)

            span.set_attribute("entities_created", len(entities))
            return entities
