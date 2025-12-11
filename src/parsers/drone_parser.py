"""
Drone Parser for CopForge.

Parser for drone telemetry and image data.
"""

from typing import Any

from src.core.telemetry import get_tracer, traced_operation
from src.models.cop import EntityCOP, Location
from src.models.sensor import SensorMessage
from src.parsers.base_parser import BaseParser

# Get tracer for this module
tracer = get_tracer("copforge.parsers.drone")


class DroneParser(BaseParser):
    """
    Parser for drone sensor data.

    Handles drone telemetry, imagery, and visual intelligence.

    Expected data format:
        {
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
            "image_link": "data/drone_alpha/IMG_001.jpg"
        }
    """

    def can_parse(self, sensor_msg: SensorMessage) -> bool:
        """Check if message is drone format."""
        if sensor_msg.sensor_type != "drone":
            return False

        data = sensor_msg.data

        # Drone data must have position
        return isinstance(data, dict) and (
            ("latitude" in data or "lat" in data) and ("longitude" in data or "lon" in data)
        )

    def validate(self, sensor_msg: SensorMessage) -> tuple[bool, str]:
        """Validate drone message structure."""
        data = sensor_msg.data

        if not isinstance(data, dict):
            return False, "Data must be a dictionary"

        # Check required fields
        if "latitude" not in data and "lat" not in data:
            return False, "Missing latitude"

        if "longitude" not in data and "lon" not in data:
            return False, "Missing longitude"

        # Validate drone_id if present
        if "drone_id" in data and not isinstance(data["drone_id"], str):
            return False, "drone_id must be a string"

        return True, ""

    def parse(self, sensor_msg: SensorMessage) -> list[EntityCOP]:
        """Parse drone data into EntityCOP objects."""
        with traced_operation(
            tracer,
            "parse_drone",
            {"sensor_id": sensor_msg.sensor_id},
        ) as span:
            data: dict[str, Any] = sensor_msg.data  # type: ignore
            entities: list[EntityCOP] = []

            # Get drone position
            lat = data.get("latitude") or data.get("lat")
            lon = data.get("longitude") or data.get("lon")
            alt_agl = data.get("altitude_m_agl")
            alt_msl = data.get("altitude_m_msl")

            # Use MSL if available, otherwise AGL
            altitude = alt_msl if alt_msl is not None else alt_agl

            location = Location(lat=lat, lon=lon, alt=altitude)

            # Drone entity (the drone itself)
            drone_id = data.get("drone_id", f"{sensor_msg.sensor_id}_platform")

            # Metadata
            metadata: dict[str, Any] = {
                "drone_id": drone_id,
                "flight_mode": data.get("flight_mode"),
                "altitude_m_agl": alt_agl,
                "altitude_m_msl": alt_msl,
                "heading": data.get("heading"),
                "ground_speed_kmh": data.get("ground_speed_kmh"),
                "battery_percent": data.get("battery_percent"),
                "camera_heading": data.get("camera_heading"),
                "sensor_type": "drone",
            }

            # Check if there's an image
            has_image = bool(data.get("image_link") or data.get("image_path"))
            if has_image:
                metadata["image_link"] = data.get("image_link") or data.get("image_path")
                span.set_attribute("has_image", True)

            # Drone classification (always friendly - it's our drone)
            # Information classification: drone position is typically CONFIDENTIAL
            drone_entity = self._create_entity(
                entity_id=drone_id,
                entity_type="uav",
                location=location,
                timestamp=sensor_msg.timestamp,
                sensor_msg=sensor_msg,
                classification="friendly",  # Our drone
                information_classification="CONFIDENTIAL",
                confidence=0.95,  # High confidence in own drone telemetry
                metadata=metadata,
                speed_kmh=data.get("ground_speed_kmh"),
                heading=data.get("heading"),
                comments=f"UAV {drone_id} telemetry",
            )

            entities.append(drone_entity)

            # If drone has image with visual intelligence, that will be processed
            # by multimodal tools and create additional entities
            # (handled in multimodal processing, not here)

            span.set_attribute("entities_created", len(entities))
            return entities
