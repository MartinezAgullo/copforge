"""Core functionality for CopForge."""

from src.core.config import Settings, get_settings
from src.core.constants import (
    ACCESS_LEVELS,
    ACCESS_TO_MAX_CLASSIFICATION,
    CLASSIFICATION_HIERARCHY,
    CLASSIFICATION_LEVEL_SET,
    CLASSIFICATION_LEVELS,
    CLASSIFICATIONS,
    ENTITY_TYPES,
    SENSOR_TYPES,
    can_access_classification,
    get_classification_level,
    is_valid_access_level,
    is_valid_classification,
    is_valid_entity_type,
    is_valid_info_classification,
    is_valid_sensor_type,
)
from src.core.telemetry import (
    get_tracer,
    setup_telemetry,
    trace_function,
    traced_operation,
)

__all__ = [
    # Config
    "Settings",
    "get_settings",
    # Telemetry
    "setup_telemetry",
    "get_tracer",
    "traced_operation",
    "trace_function",
    # Constants
    "SENSOR_TYPES",
    "CLASSIFICATIONS",
    "CLASSIFICATION_LEVELS",
    "CLASSIFICATION_LEVEL_SET",
    "CLASSIFICATION_HIERARCHY",
    "ACCESS_LEVELS",
    "ACCESS_TO_MAX_CLASSIFICATION",
    "ENTITY_TYPES",
    "can_access_classification",
    "get_classification_level",
    "is_valid_sensor_type",
    "is_valid_classification",
    "is_valid_info_classification",
    "is_valid_access_level",
    "is_valid_entity_type",
]
