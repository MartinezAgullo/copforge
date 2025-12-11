"""
Manual Report Parser for CopForge.

Parser for human-generated situation reports.
"""

from typing import Any

from src.core.telemetry import get_tracer, traced_operation
from src.models.cop import EntityCOP, Location
from src.models.sensor import SensorMessage
from src.parsers.base_parser import BaseParser

# Get tracer for this module
tracer = get_tracer("copforge.parsers.manual")


class ManualParser(BaseParser):
    """
    Parser for manual operator reports.

    Handles SITREP, SPOTREP, SALUTE, and other military report formats.

    Expected data format:
        {
            "report_id": "SPOTREP_001",
            "report_type": "SPOTREP",
            "priority": "high",
            "operator_name": "Cpt. Smith",
            "content": "Visual confirmation: Single military aircraft, no IFF response",
            "latitude": 39.50,
            "longitude": -0.35,
            "altitude_m": null
        }

    Supported report types:
        - SITREP: Situation Report
        - SPOTREP: Spot Report
        - SALUTE: Size, Activity, Location, Unit, Time, Equipment
        - LOGREP: Logistics Report
        - MEDEVAC: Medical Evacuation Request
        - OTHER: Generic report
    """

    def can_parse(self, sensor_msg: SensorMessage) -> bool:
        """Check if message is manual report format."""
        if sensor_msg.sensor_type != "manual":
            return False

        data = sensor_msg.data

        # Manual reports must have operator_name and content
        return isinstance(data, dict) and "operator_name" in data and "content" in data

    def validate(self, sensor_msg: SensorMessage) -> tuple[bool, str]:
        """Validate manual report structure."""
        data = sensor_msg.data

        if not isinstance(data, dict):
            return False, "Data must be a dictionary"

        # Check required fields
        required = ["operator_name", "content", "priority"]
        missing = [field for field in required if field not in data]
        if missing:
            return False, f"Missing required fields: {missing}"

        # Validate priority
        valid_priorities = ["low", "medium", "high", "critical"]
        if data.get("priority") not in valid_priorities:
            return False, f"Invalid priority. Must be one of: {valid_priorities}"

        return True, ""

    def parse(self, sensor_msg: SensorMessage) -> list[EntityCOP]:
        """
        Parse manual report into EntityCOP.

        Creates an event entity representing the reported observation.
        LLM may later extract specific entities from the report content
        via multimodal processing.
        """
        with traced_operation(
            tracer,
            "parse_manual",
            {"sensor_id": sensor_msg.sensor_id},
        ) as span:
            data: dict[str, Any] = sensor_msg.data  # type: ignore
            entities: list[EntityCOP] = []

            # Check if report has location
            if "latitude" not in data or "longitude" not in data:
                span.set_attribute("skipped", True)
                span.set_attribute("skip_reason", "no_location")
                # No specific location - skip entity creation
                return entities

            location = Location(
                lat=data["latitude"],
                lon=data["longitude"],
                alt=data.get("altitude_m"),
            )

            # Build entity ID
            report_id = data.get("report_id", f"{sensor_msg.sensor_id}_report")
            entity_id = f"{sensor_msg.sensor_id}_{report_id}"

            # Metadata
            metadata: dict[str, Any] = {
                "report_id": report_id,
                "report_type": data.get("report_type", "OTHER"),
                "priority": data["priority"],
                "operator_name": data["operator_name"],
                "content": data["content"],
                "sensor_type": "manual",
            }

            span.set_attribute("report_type", metadata["report_type"])
            span.set_attribute("priority", metadata["priority"])

            # Determine classification based on priority and report type
            priority = data["priority"]
            if priority == "critical":
                info_classification = "SECRET"
            elif priority == "high":
                info_classification = "CONFIDENTIAL"
            else:
                info_classification = "RESTRICTED"

            # Allow override if specified
            info_classification = data.get("classification_level", info_classification)

            # Determine confidence based on operator and priority
            # High priority reports from known operators have higher confidence
            confidence = 0.85 if priority in ["critical", "high"] else 0.7
            # if priority in ["critical", "high"]:
            #     confidence = 0.85
            # else:
            #     confidence = 0.7

            # Truncate content for comments (first 100 chars)
            content_preview = data["content"][:100]
            if len(data["content"]) > 100:
                content_preview += "..."

            # Create event entity
            report_entity = self._create_entity(
                entity_id=entity_id,
                entity_type="event",
                location=location,
                timestamp=sensor_msg.timestamp,
                sensor_msg=sensor_msg,
                classification="unknown",  # Will be determined from content analysis
                information_classification=info_classification,
                confidence=confidence,
                metadata=metadata,
                comments=f"{data.get('report_type', 'REPORT')} from {data['operator_name']}: {content_preview}",
            )

            entities.append(report_entity)

            span.set_attribute("entities_created", len(entities))
            return entities
