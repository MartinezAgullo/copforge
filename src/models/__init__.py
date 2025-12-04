"""
CopForge data models.

This package contains all Pydantic models for the CopForge system:
- COP models: EntityCOP, Location, ThreatAssessment, COPSnapshot
- Sensor models: SensorMessage, and format-specific models (ASTERIX, Drone, etc.)
"""

from src.models.cop import (
    # Type aliases
    AccessLevel,
    ClassificationType,
    COPSnapshot,
    EntityCOP,
    EntityType,
    InfoClassificationLevel,
    Location,
    ThreatAssessment,
)
from src.models.sensor import (
    # Format-specific models
    ASTERIXMessage,
    ASTERIXTrack,
    DroneData,
    # Core models
    FileReference,
    # Type aliases
    FileType,
    ManualReport,
    RadioData,
    SensorMessage,
    SensorMessageBatch,
    SensorType,
    TrackQuality,
)

__all__ = [
    # COP models
    "EntityCOP",
    "Location",
    "ThreatAssessment",
    "COPSnapshot",
    # COP types
    "ClassificationType",
    "InfoClassificationLevel",
    "EntityType",
    "AccessLevel",
    # Sensor models
    "SensorMessage",
    "SensorMessageBatch",
    "FileReference",
    "ASTERIXMessage",
    "ASTERIXTrack",
    "DroneData",
    "RadioData",
    "ManualReport",
    "TrackQuality",
    # Sensor types
    "SensorType",
    "FileType",
]
