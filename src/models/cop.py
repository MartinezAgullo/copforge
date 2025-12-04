"""
COP (Common Operational Picture) data models.

These models represent normalized entities in the operational picture,
regardless of their original sensor source.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Type Definitions
# =============================================================================

# Valid IFF classifications (Identification Friend or Foe)
ClassificationType = Literal["friendly", "hostile", "neutral", "unknown"]

# Information classification levels (security clearance)
InfoClassificationLevel = Literal[
    "UNCLASSIFIED",
    "RESTRICTED",
    "CONFIDENTIAL",
    "SECRET",
    "TOP_SECRET",
]

# Entity types - comprehensive list for tactical scenarios
EntityType = Literal[
    # Air
    "aircraft",
    "fighter",
    "bomber",
    "helicopter",
    "uav",
    "missile",
    # Ground
    "ground_vehicle",
    "tank",
    "apc",
    "artillery",
    "infantry",
    # Sea
    "ship",
    "destroyer",
    "submarine",
    # Infrastructure
    "base",
    "building",
    "infrastructure",
    # Other
    "person",
    "event",
    "unknown",
]

# Access levels for dissemination control
AccessLevel = Literal[
    "top_secret_access",
    "secret_access",
    "confidential_access",
    "restricted_access",
    "unclassified_access",
    "enemy_access",  # For deception operations
]


# =============================================================================
# Core Models
# =============================================================================


class Location(BaseModel):
    """Geographic location with optional altitude."""

    lat: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")
    alt: float | None = Field(default=None, description="Altitude in meters")

    @field_validator("lat", "lon", mode="after")
    @classmethod
    def round_coordinates(cls, v: float) -> float:
        """Round to 6 decimal places (~0.1m precision)."""
        return round(v, 6)

    def to_tuple(self) -> tuple[float, float] | tuple[float, float, float]:
        """Return location as tuple (lat, lon) or (lat, lon, alt)."""
        if self.alt is not None:
            return (self.lat, self.lon, self.alt)
        return (self.lat, self.lon)

    def __str__(self) -> str:
        """Human-readable string representation."""
        if self.alt is not None:
            return f"({self.lat:.4f}, {self.lon:.4f}, {self.alt:.0f}m)"
        return f"({self.lat:.4f}, {self.lon:.4f})"


class EntityCOP(BaseModel):
    """
    Common Operational Picture Entity.

    Represents any tracked entity in the operational environment: aircraft,
    vehicles, infrastructure, persons, events, etc. This is the universal
    format for all entities, regardless of their original sensor source.
    """

    # Identity
    entity_id: str = Field(..., description="Unique identifier for this entity")
    entity_type: EntityType = Field(default="unknown", description="Type of entity")

    # Position and movement
    location: Location = Field(..., description="Current geographic location")
    heading: float | None = Field(default=None, ge=0, lt=360, description="Heading in degrees")
    speed_kmh: float | None = Field(default=None, ge=0, description="Speed in km/h")

    # Classification
    classification: ClassificationType = Field(
        default="unknown",
        description="IFF classification (friendly, hostile, neutral, unknown)",
    )
    information_classification: InfoClassificationLevel = Field(
        default="UNCLASSIFIED",
        description="Security classification level of this entity's information",
    )

    # Confidence and tracking
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence in this information (0.0-1.0)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this information was recorded",
    )

    # Source tracking (for sensor fusion)
    source_sensors: list[str] = Field(
        default_factory=list,
        description="List of sensor IDs that reported this entity",
    )

    # Additional data
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional sensor-specific metadata",
    )
    comments: str | None = Field(default=None, description="Human-readable comments")

    @field_validator("classification", mode="before")
    @classmethod
    def normalize_classification(cls, v: str) -> str:
        """Normalize classification to lowercase."""
        if isinstance(v, str):
            return v.lower()
        return v

    @field_validator("information_classification", mode="before")
    @classmethod
    def normalize_info_classification(cls, v: str) -> str:
        """Normalize information classification to uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v

    def model_dump_json_safe(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (handles datetime)."""
        data = self.model_dump()
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def __str__(self) -> str:
        """Human-readable string representation."""
        return (
            f"EntityCOP({self.entity_id}, {self.entity_type}, "
            f"{self.classification}, {self.location})"
        )

    model_config = {
        "json_schema_extra": {
            "example": {
                "entity_id": "radar_01_T001",
                "entity_type": "aircraft",
                "location": {"lat": 39.5, "lon": -0.4, "alt": 5000},
                "timestamp": "2025-10-15T14:30:00Z",
                "classification": "unknown",
                "information_classification": "SECRET",
                "confidence": 0.9,
                "source_sensors": ["radar_01"],
                "metadata": {"track_id": "T001", "speed_kmh": 450},
                "speed_kmh": 450,
                "heading": 270,
            }
        }
    }


class ThreatAssessment(BaseModel):
    """
    Threat evaluation for a specific entity or situation.

    Generated by threat evaluation logic to assess risks to friendly assets.
    """

    assessment_id: str = Field(..., description="Unique ID for this assessment")
    threat_level: Literal["critical", "high", "medium", "low", "none"] = Field(
        ..., description="Severity of the threat"
    )

    # What is threatened
    affected_entities: list[str] = Field(
        ..., description="List of entity IDs that are affected by this threat"
    )

    # What is threatening
    threat_source_id: str | None = Field(
        default=None, description="Entity ID of the threat source (if applicable)"
    )

    # Assessment details
    reasoning: str = Field(..., description="Natural language explanation of the threat")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this assessment")
    timestamp: datetime = Field(..., description="When this assessment was made")

    # Geospatial context
    distances_to_affected_km: dict[str, float] | None = Field(
        default=None,
        description="Distance from threat to each affected entity (entity_id -> km)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "assessment_id": "threat_001",
                "threat_level": "high",
                "affected_entities": ["radar_base_01", "command_post_alpha"],
                "threat_source_id": "aircraft_T001",
                "reasoning": "Unknown aircraft approaching restricted airspace at high speed",
                "confidence": 0.85,
                "timestamp": "2025-10-15T14:30:00Z",
                "distances_to_affected_km": {
                    "radar_base_01": 45.2,
                    "command_post_alpha": 52.8,
                },
            }
        }
    }


class COPSnapshot(BaseModel):
    """
    Snapshot of the entire Common Operational Picture at a point in time.

    Used for checkpointing, audit trail, and state recovery.
    """

    snapshot_id: str = Field(..., description="Unique identifier for this snapshot")
    timestamp: datetime = Field(..., description="When this snapshot was taken")
    entities: dict[str, EntityCOP] = Field(
        default_factory=dict,
        description="All entities in the COP (entity_id -> EntityCOP)",
    )
    threat_assessments: list[ThreatAssessment] = Field(
        default_factory=list, description="Active threat assessments"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional snapshot metadata"
    )
