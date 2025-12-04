"""
Sensor message data models.

These models represent raw input from various sensor sources
before normalization into EntityCOP format.

Based on TIFDA's sensor_formats.py with improvements for modularity.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Type Definitions
# =============================================================================

# Supported sensor types
SensorType = Literal[
    "radar",
    "drone",
    "manual",
    "radio",
    "ais",  # Automatic Identification System (ships)
    "ads-b",  # Automatic Dependent Surveillance-Broadcast (aircraft)
    "link16",  # Tactical data link
    "acoustic",  # Acoustic sensors (sonar, microphones)
    "sigint",  # Signals intelligence
    "imint",  # Imagery intelligence
    "other",
]

# File types for multimodal processing
FileType = Literal["audio", "image", "document", "video", "unknown"]


# =============================================================================
# Core Sensor Models
# =============================================================================


class SensorMessage(BaseModel):
    """
    Raw sensor message before processing.

    This is the universal input format for the Ingest Agent. Each sensor type
    may have different data structures in the 'data' field, but all share
    this common envelope.
    """

    # Sensor identification
    sensor_id: str = Field(..., description="Unique identifier of the sensor")
    sensor_type: SensorType = Field(..., description="Type of sensor")

    # Timing
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Message timestamp",
    )

    # Payload - can be dict (structured) or str (raw text/format)
    data: dict[str, Any] | str = Field(..., description="Sensor data payload")

    # Optional metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (e.g., signal strength, encoding)",
    )

    # File references (for multimodal processing)
    file_references: dict[str, str] = Field(
        default_factory=dict,
        description="File references (e.g., {'image': '/path/to/img.jpg'})",
    )

    @field_validator("sensor_type", mode="before")
    @classmethod
    def normalize_sensor_type(cls, v: str) -> str:
        """Normalize sensor type to lowercase."""
        if isinstance(v, str):
            return v.lower()
        return v

    def has_file_references(self) -> bool:
        """Check if message has file references requiring multimodal processing."""
        if self.file_references:
            return True

        # Also check within data dict for common file reference keys
        if isinstance(self.data, dict):
            file_keys = {
                "image_link",
                "image_path",
                "audio_link",
                "audio_path",
                "document_link",
                "document_path",
                "file_path",
                "video_path",
                "attachment",
            }
            return bool(file_keys & set(self.data.keys()))

        return False

    def get_file_references(self) -> dict[str, str]:
        """
        Extract all file references from the message.

        Returns:
            Dict mapping file type to file path.
        """
        refs = dict(self.file_references)

        # Extract from data dict
        if isinstance(self.data, dict):
            file_key_mapping = {
                "image_link": "image",
                "image_path": "image",
                "audio_link": "audio",
                "audio_path": "audio",
                "document_link": "document",
                "document_path": "document",
                "file_path": "file",
                "video_path": "video",
                "attachment": "attachment",
            }
            for key, file_type in file_key_mapping.items():
                if key in self.data and self.data[key]:
                    refs[file_type] = self.data[key]

        return refs

    def model_dump_json_safe(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (handles datetime)."""
        data = self.model_dump()
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"SensorMessage({self.sensor_id}, {self.sensor_type}, {self.timestamp.isoformat()})"

    model_config = {
        "json_schema_extra": {
            "examples": [
                # Radar with inline data
                {
                    "sensor_id": "radar_01",
                    "sensor_type": "radar",
                    "timestamp": "2025-10-15T14:30:00Z",
                    "data": {
                        "format": "asterix",
                        "system_id": "ES_RAD_101",
                        "tracks": [
                            {
                                "track_id": "T001",
                                "location": {"lat": 39.5, "lon": -0.4},
                                "altitude_m": 5000,
                                "speed_kmh": 450,
                            }
                        ],
                    },
                },
                # Drone with image reference
                {
                    "sensor_id": "drone_alpha",
                    "sensor_type": "drone",
                    "timestamp": "2025-10-15T14:31:00Z",
                    "data": {
                        "drone_id": "DRONE_ALPHA_01",
                        "latitude": 39.4762,
                        "longitude": -0.3747,
                        "altitude_m_agl": 120,
                        "image_link": "data/drone_alpha/IMG_001.jpg",
                    },
                },
            ]
        }
    }


class SensorMessageBatch(BaseModel):
    """Batch of sensor messages for bulk processing."""

    messages: list[SensorMessage] = Field(..., description="List of sensor messages")
    batch_id: str | None = Field(default=None, description="Optional batch identifier")
    source: str | None = Field(default=None, description="Batch source identifier")

    def __len__(self) -> int:
        """Return number of messages in batch."""
        return len(self.messages)

    def __iter__(self) -> Any:
        """Iterate over messages."""
        return iter(self.messages)


# =============================================================================
# Sensor-Specific Data Models (for validation and documentation)
# =============================================================================


class TrackQuality(BaseModel):
    """Quality metrics for radar tracks."""

    accuracy_m: float | None = Field(
        default=None, description="Estimated position accuracy in meters"
    )
    plot_count: int | None = Field(
        default=None, description="Number of plots used to generate this track"
    )
    ssr_code: str | None = Field(default=None, description="SSR transponder code (if available)")


class ASTERIXTrack(BaseModel):
    """Single radar track in ASTERIX format."""

    track_id: str = Field(..., description="Track identifier")
    location: dict[str, float] = Field(..., description="Lat/lon coordinates")
    altitude_m: float | None = Field(default=None, description="Altitude in meters")
    speed_kmh: float = Field(..., description="Speed in km/h")
    heading: float | None = Field(default=None, ge=0, lt=360, description="Heading in degrees")
    classification: str | None = Field(default=None, description="Target classification")
    quality: TrackQuality | None = Field(default=None, description="Track quality metrics")


class ASTERIXMessage(BaseModel):
    """ASTERIX radar message format (simplified JSON representation)."""

    format: Literal["asterix"] = "asterix"
    system_id: str = Field(..., description="Radar system identifier")
    timestamp: datetime | None = Field(default=None, description="Message timestamp")
    is_simulated: bool = Field(default=False, description="Whether this is simulated data")
    tracks: list[ASTERIXTrack] = Field(default_factory=list, description="List of tracks")

    model_config = {
        "json_schema_extra": {
            "example": {
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
                    }
                ],
            }
        }
    }


class DroneData(BaseModel):
    """Drone telemetry and image data."""

    drone_id: str = Field(..., description="Unique identifier for the drone")
    timestamp: datetime | None = Field(default=None, description="Telemetry timestamp")
    flight_mode: Literal["manual", "auto", "loiter", "rtl", "mission"] = Field(
        ..., description="Current flight mode"
    )
    latitude: float = Field(..., ge=-90, le=90, description="Latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude")
    altitude_m_agl: float = Field(..., description="Altitude Above Ground Level (meters)")
    altitude_m_msl: float | None = Field(
        default=None, description="Altitude Above Mean Sea Level (meters)"
    )
    heading: float | None = Field(default=None, ge=0, lt=360, description="Heading in degrees")
    ground_speed_kmh: float | None = Field(default=None, description="Ground speed in km/h")
    battery_percent: float | None = Field(default=None, ge=0, le=100, description="Battery level")
    camera_heading: float | None = Field(default=None, description="Camera gimbal heading")
    image_link: str | None = Field(default=None, description="Path/URL to captured image")

    model_config = {
        "json_schema_extra": {
            "example": {
                "drone_id": "DRONE_ALPHA_01",
                "flight_mode": "auto",
                "latitude": 39.4762,
                "longitude": -0.3747,
                "altitude_m_agl": 120,
                "altitude_m_msl": 145,
                "heading": 90,
                "ground_speed_kmh": 45,
                "battery_percent": 78,
                "image_link": "data/drone_alpha/IMG_001.jpg",
            }
        }
    }


class RadioData(BaseModel):
    """Radio communication interception metadata."""

    station_id: str = Field(..., description="Unique ID of the intercept station")
    timestamp: datetime | None = Field(default=None, description="Start of transmission")
    frequency_mhz: float = Field(..., description="Carrier frequency (MHz)")
    bandwidth_khz: float = Field(..., description="Signal bandwidth (kHz)")
    modulation_type: Literal["AM", "FM", "SSB", "FSK", "DMR", "other"] = Field(
        ..., description="Detected modulation type"
    )
    channel: str = Field(..., description="Radio channel identifier")
    duration_sec: float = Field(..., description="Transmission duration in seconds")
    signal_strength: float | None = Field(default=None, description="Signal strength in dBm")
    audio_path: str | None = Field(default=None, description="Path to recorded audio file")

    model_config = {
        "json_schema_extra": {
            "example": {
                "station_id": "INTERCEPT_BRAVO_01",
                "frequency_mhz": 145.500,
                "bandwidth_khz": 12.5,
                "modulation_type": "FM",
                "channel": "tactical_01",
                "duration_sec": 45,
                "signal_strength": -72,
                "audio_path": "data/radio_bravo/transmission_143200.mp3",
            }
        }
    }


class ManualReport(BaseModel):
    """Human-generated situation report."""

    report_id: str | None = Field(default=None, description="Unique report identifier")
    timestamp: datetime | None = Field(default=None, description="Report creation time")
    report_type: Literal["SITREP", "SPOTREP", "SALUTE", "LOGREP", "MEDEVAC", "OTHER"] = Field(
        default="OTHER", description="Military report type"
    )
    priority: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Report priority"
    )
    operator_name: str = Field(..., description="Name or ID of reporting operator")
    content: str = Field(..., description="Report text content")
    latitude: float | None = Field(default=None, ge=-90, le=90, description="Latitude of event")
    longitude: float | None = Field(default=None, ge=-180, le=180, description="Longitude of event")
    altitude_m: float | None = Field(default=None, description="Altitude of event in meters")

    model_config = {
        "json_schema_extra": {
            "example": {
                "report_id": "SPOTREP_001",
                "report_type": "SPOTREP",
                "priority": "high",
                "operator_name": "Cpt. Smith",
                "content": "Visual confirmation: Single military aircraft, no IFF response",
                "latitude": 39.50,
                "longitude": -0.35,
            }
        }
    }


# =============================================================================
# File Reference Model
# =============================================================================


class FileReference(BaseModel):
    """Reference to an external file for multimodal processing."""

    file_type: FileType = Field(..., description="Type of file")
    file_path: str = Field(..., description="Path to file (absolute or relative)")
    file_size_mb: float | None = Field(default=None, description="File size in megabytes")
    mime_type: str | None = Field(default=None, description="MIME type of the file")

    model_config = {
        "json_schema_extra": {
            "example": {
                "file_type": "audio",
                "file_path": "data/radio_bravo/transmission_143200.mp3",
                "file_size_mb": 1.1,
                "mime_type": "audio/mpeg",
            }
        }
    }
