"""
Constants and configuration values for CopForge.

Centralized definitions for sensor types, classifications, access levels,
and other configuration that needs to be consistent across the system.
"""


# =============================================================================
# Sensor Types
# =============================================================================

SENSOR_TYPES: set[str] = {
    "radar",
    "drone",
    "manual",
    "radio",
    "ais",
    "ads-b",
    "link16",
    "acoustic",
    "sigint",
    "imint",
    "other",
}

# =============================================================================
# IFF Classifications (Identification Friend or Foe)
# =============================================================================

CLASSIFICATIONS: set[str] = {
    "friendly",
    "hostile",
    "neutral",
    "unknown",
}

# =============================================================================
# Information Classification Levels (Security)
# =============================================================================

# Ordered from highest to lowest
CLASSIFICATION_LEVELS: list[str] = [
    "TOP_SECRET",
    "SECRET",
    "CONFIDENTIAL",
    "RESTRICTED",
    "UNCLASSIFIED",
]

CLASSIFICATION_LEVEL_SET: set[str] = set(CLASSIFICATION_LEVELS)

# Numeric hierarchy for comparison (higher = more restricted)
CLASSIFICATION_HIERARCHY: dict[str, int] = {
    "UNCLASSIFIED": 0,
    "RESTRICTED": 1,
    "CONFIDENTIAL": 2,
    "SECRET": 3,
    "TOP_SECRET": 4,
}

# =============================================================================
# Access Levels (for dissemination control)
# =============================================================================

ACCESS_LEVELS: set[str] = {
    "top_secret_access",
    "secret_access",
    "confidential_access",
    "restricted_access",
    "unclassified_access",
    "enemy_access",  # Special: for deception operations
}

# Mapping of access level to maximum classification it can read
ACCESS_TO_MAX_CLASSIFICATION: dict[str, str] = {
    "top_secret_access": "TOP_SECRET",
    "secret_access": "SECRET",
    "confidential_access": "CONFIDENTIAL",
    "restricted_access": "RESTRICTED",
    "unclassified_access": "UNCLASSIFIED",
    "enemy_access": "UNCLASSIFIED",  # Enemy can only see UNCLASSIFIED
}

# =============================================================================
# Entity Types
# =============================================================================

ENTITY_TYPES: set[str] = {
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
}

# =============================================================================
# Helper Functions
# =============================================================================


def can_access_classification(access_level: str, classification: str) -> bool:
    """
    Check if an access level can view a given classification.

    Implements the "read-down" principle: users can read at or below their level.

    Args:
        access_level: User's access level (e.g., "secret_access")
        classification: Information classification (e.g., "CONFIDENTIAL")

    Returns:
        True if access is permitted, False otherwise
    """
    if access_level not in ACCESS_TO_MAX_CLASSIFICATION:
        return False

    if classification not in CLASSIFICATION_HIERARCHY:
        return False

    max_allowed = ACCESS_TO_MAX_CLASSIFICATION[access_level]
    max_level = CLASSIFICATION_HIERARCHY[max_allowed]
    requested_level = CLASSIFICATION_HIERARCHY[classification]

    return requested_level <= max_level


def get_classification_level(classification: str) -> int:
    """
    Get numeric level for a classification (for comparison).

    Args:
        classification: Classification string (e.g., "SECRET")

    Returns:
        Numeric level (higher = more restricted)
    """
    return CLASSIFICATION_HIERARCHY.get(classification.upper(), 0)


def is_valid_sensor_type(sensor_type: str) -> bool:
    """Check if sensor type is valid."""
    return sensor_type.lower() in SENSOR_TYPES


def is_valid_classification(classification: str) -> bool:
    """Check if IFF classification is valid."""
    return classification.lower() in CLASSIFICATIONS


def is_valid_info_classification(info_class: str) -> bool:
    """Check if information classification level is valid."""
    return info_class.upper() in CLASSIFICATION_LEVEL_SET


def is_valid_access_level(access_level: str) -> bool:
    """Check if access level is valid."""
    return access_level.lower() in ACCESS_LEVELS


def is_valid_entity_type(entity_type: str) -> bool:
    """Check if entity type is valid."""
    return entity_type.lower() in ENTITY_TYPES
