"""
Base Parser for CopForge.

Abstract base class for all format-specific parsers.
Each parser is responsible for converting sensor-specific data formats
into standardized EntityCOP objects for the Common Operational Picture.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from src.models.cop import EntityCOP, Location
from src.models.sensor import SensorMessage


class BaseParser(ABC):
    """
    Abstract base for all sensor format parsers.

    Each parser is responsible for converting sensor-specific data formats
    into standardized EntityCOP objects for the Common Operational Picture.

    Subclasses must implement:
        - can_parse(): Check if parser handles this message type
        - validate(): Validate message structure
        - parse(): Convert message to EntityCOP objects

    Example:
        >>> class MyParser(BaseParser):
        ...     def can_parse(self, msg): ...
        ...     def validate(self, msg): ...
        ...     def parse(self, msg): ...
    """

    @abstractmethod
    def can_parse(self, sensor_msg: SensorMessage) -> bool:
        """
        Determine if this parser can handle the sensor message format.

        Args:
            sensor_msg: Sensor message to check.

        Returns:
            True if parser recognizes and can handle this format.
        """
        pass

    @abstractmethod
    def parse(self, sensor_msg: SensorMessage) -> list[EntityCOP]:
        """
        Parse sensor message into EntityCOP objects.

        Args:
            sensor_msg: Sensor message to parse.

        Returns:
            List of EntityCOP objects extracted from the message.

        Raises:
            ValueError: If parsing fails due to invalid data.
        """
        pass

    @abstractmethod
    def validate(self, sensor_msg: SensorMessage) -> tuple[bool, str]:
        """
        Validate sensor message structure before parsing.

        Args:
            sensor_msg: Sensor message to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        pass

    def _determine_classification(
        self,
        sensor_msg: SensorMessage,
        entity_data: dict[str, Any],
    ) -> str:
        """
        Determine information classification level for entity.

        Default implementation: uses sensor metadata or defaults to UNCLASSIFIED.
        Override in subclasses for sensor-specific logic.

        Args:
            sensor_msg: Source sensor message.
            entity_data: Parsed entity data.

        Returns:
            Classification level (TOP_SECRET, SECRET, CONFIDENTIAL, RESTRICTED, UNCLASSIFIED).
        """
        # Check if classification specified in sensor data
        if isinstance(sensor_msg.data, dict) and "classification_level" in sensor_msg.data:
            return str(sensor_msg.data["classification_level"])

        # Check entity-specific classification
        if "classification_level" in entity_data:
            return str(entity_data["classification_level"])

        # Default to UNCLASSIFIED
        return "UNCLASSIFIED"

    def _create_entity(
        self,
        entity_id: str,
        entity_type: str,
        location: Location,
        timestamp: datetime,
        sensor_msg: SensorMessage,
        classification: str = "unknown",
        information_classification: str = "UNCLASSIFIED",
        confidence: float = 0.8,
        metadata: dict[str, Any] | None = None,
        speed_kmh: float | None = None,
        heading: float | None = None,
        comments: str | None = None,
    ) -> EntityCOP:
        """
        Helper to create EntityCOP with standard fields.

        Args:
            entity_id: Unique entity identifier.
            entity_type: Type of entity.
            location: Geographic location.
            timestamp: When entity was observed.
            sensor_msg: Source sensor message.
            classification: IFF classification (friendly/hostile/neutral/unknown).
            information_classification: Security classification level.
            confidence: Confidence in data (0.0-1.0).
            metadata: Additional metadata.
            speed_kmh: Speed in km/h (optional).
            heading: Heading in degrees (optional).
            comments: Human-readable comments (optional).

        Returns:
            EntityCOP object.
        """
        return EntityCOP(
            entity_id=entity_id,
            entity_type=entity_type,
            location=location,
            timestamp=timestamp,
            classification=classification,
            information_classification=information_classification,
            confidence=confidence,
            source_sensors=[sensor_msg.sensor_id],
            metadata=metadata or {},
            speed_kmh=speed_kmh,
            heading=heading,
            comments=comments,
        )
