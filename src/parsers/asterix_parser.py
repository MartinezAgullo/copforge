"""
ASTERIX Parser for CopForge.

Parser for ASTERIX radar format (simplified JSON representation).
ASTERIX is the standard for radar data exchange in European airspace.
"""

from typing import Any

from src.core.telemetry import get_tracer, traced_operation
from src.models.cop import EntityCOP, Location
from src.models.sensor import SensorMessage
from src.parsers.base_parser import BaseParser

# Get tracer for this module
tracer = get_tracer("copforge.parsers.asterix")


class ASTERIXParser(BaseParser):
    """
    Parser for ASTERIX radar format.

    Handles radar track data in JSON format representing ASTERIX messages.
    ASTERIX (All Purpose Structured Eurocontrol Surveillance Information Exchange)
    is the standard for radar data exchange.

    Expected data format:
        {
            "format": "asterix",
            "system_id": "ES_RAD_101",
            "is_simulated": false,
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
                        "ssr_code": "7700"
                    }
                }
            ]
        }
    """

    def can_parse(self, sensor_msg: SensorMessage) -> bool:
        """Check if message is ASTERIX format."""
        # Check sensor type
        if sensor_msg.sensor_type != "radar":
            return False

        # Check for ASTERIX format indicator
        data = sensor_msg.data
        return isinstance(data, dict) and data.get("format") == "asterix" and "tracks" in data

    def validate(self, sensor_msg: SensorMessage) -> tuple[bool, str]:
        """Validate ASTERIX message structure."""
        data = sensor_msg.data

        if not isinstance(data, dict):
            return False, "Data must be a dictionary"

        # Check required top-level fields
        if "tracks" not in data:
            return False, "Missing 'tracks' array"

        if not isinstance(data["tracks"], list):
            return False, "'tracks' must be an array"

        # Validate each track
        for i, track in enumerate(data["tracks"]):
            if not isinstance(track, dict):
                return False, f"Track {i} must be an object"

            # Required fields
            required = ["track_id", "location", "speed_kmh"]
            missing = [field for field in required if field not in track]
            if missing:
                return False, f"Track {i} missing required fields: {missing}"

            # Validate location
            location = track.get("location")
            if not isinstance(location, dict):
                return False, f"Track {i} location must be an object"

            if "lat" not in location or "lon" not in location:
                return False, f"Track {i} location must have 'lat' and 'lon'"

        return True, ""

    def parse(self, sensor_msg: SensorMessage) -> list[EntityCOP]:
        """Parse ASTERIX tracks into EntityCOP objects."""
        with traced_operation(
            tracer,
            "parse_asterix",
            {
                "sensor_id": sensor_msg.sensor_id,
                "track_count": len(sensor_msg.data.get("tracks", [])),  # type: ignore
            },
        ) as span:
            data: dict[str, Any] = sensor_msg.data  # type: ignore
            entities: list[EntityCOP] = []

            # Get system-level metadata
            system_id = data.get("system_id", sensor_msg.sensor_id)
            is_simulated = data.get("is_simulated", False)

            # Determine base classification for radar data
            # Radar data is typically SECRET or CONFIDENTIAL
            base_classification = data.get("classification_level", "SECRET")

            for track in data["tracks"]:
                entity = self._parse_track(
                    track=track,
                    sensor_msg=sensor_msg,
                    system_id=system_id,
                    is_simulated=is_simulated,
                    base_classification=base_classification,
                )
                entities.append(entity)

            span.set_attribute("entities_created", len(entities))
            return entities

    def _parse_track(
        self,
        track: dict[str, Any],
        sensor_msg: SensorMessage,
        system_id: str,
        is_simulated: bool,
        base_classification: str,
    ) -> EntityCOP:
        """Parse a single ASTERIX track into EntityCOP."""
        # Build entity ID
        track_id = track["track_id"]
        entity_id = f"{sensor_msg.sensor_id}_{track_id}"

        # Parse location
        loc_data = track["location"]
        location = Location(
            lat=loc_data["lat"],
            lon=loc_data["lon"],
            alt=track.get("altitude_m"),
        )

        # Determine entity type (radar detects air targets)
        entity_type = "aircraft"  # Default for radar
        altitude = track.get("altitude_m", 0)
        if altitude is not None and altitude < 100:
            entity_type = "ground_vehicle"  # Low altitude might be ground

        # Parse IFF classification
        iff_classification = track.get("classification", "unknown")
        if iff_classification not in ["friendly", "hostile", "neutral", "unknown"]:
            iff_classification = "unknown"

        # Build metadata
        metadata: dict[str, Any] = {
            "track_id": track_id,
            "system_id": system_id,
            "is_simulated": is_simulated,
            "altitude_m": track.get("altitude_m"),
            "speed_kmh": track["speed_kmh"],
            "heading": track.get("heading"),
            "sensor_type": "radar",
        }

        # Add quality data if available
        confidence = 0.8  # Default radar confidence
        info_classification = base_classification

        if "quality" in track:
            quality = track["quality"]
            metadata["quality"] = {
                "accuracy_m": quality.get("accuracy_m"),
                "plot_count": quality.get("plot_count"),
                "ssr_code": quality.get("ssr_code"),
            }

            # Higher plot count = higher confidence
            plot_count = quality.get("plot_count", 1)
            confidence = min(0.5 + (plot_count * 0.1), 0.95)

            # If SSR code present (transponder), might be friendlier data
            if quality.get("ssr_code"):
                info_classification = "CONFIDENTIAL"

        # Create entity
        return self._create_entity(
            entity_id=entity_id,
            entity_type=entity_type,
            location=location,
            timestamp=sensor_msg.timestamp,
            sensor_msg=sensor_msg,
            classification=iff_classification,
            information_classification=info_classification,
            confidence=confidence,
            metadata=metadata,
            speed_kmh=track["speed_kmh"],
            heading=track.get("heading"),
            comments=f"Radar track {track_id} from {system_id}",
        )
