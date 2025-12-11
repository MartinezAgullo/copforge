"""
CopForge Security Firewall.

Multi-layer security validation for incoming sensor data.

Protects against:
- Prompt injection attacks
- Malformed data structures
- Unauthorized sensors
- Invalid coordinates
- Classification/access control violations

Usage:
    from src.security.firewall import validate_sensor_input, validate_entity

    # Validate incoming sensor message
    result = validate_sensor_input(sensor_msg)
    if not result.is_valid:
        logger.error(f"Blocked: {result.error}")

    # Validate entity before adding to COP
    result = validate_entity(entity)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from src.core.constants import (
    ACCESS_LEVELS,
    CLASSIFICATION_LEVEL_SET,
    CLASSIFICATIONS,
    SENSOR_TYPES,
    can_access_classification,
)

if TYPE_CHECKING:
    from src.models.cop import EntityCOP
    from src.models.sensor import SensorMessage


# =============================================================================
# Validation Result
# =============================================================================


@dataclass
class ValidationResult:
    """Result of a firewall validation check."""

    is_valid: bool
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.is_valid


# =============================================================================
# Suspicious Patterns
# =============================================================================

# Common prompt injection patterns
PROMPT_INJECTION_PATTERNS: list[str] = [
    # Instruction override attempts
    r"ignore\s+(previous|above|all|your)\s+(instructions?|prompts?|rules?)",
    r"disregard\s+(previous|above|all)\s+(instructions?|prompts?)",
    r"forget\s+(everything|all|previous|your)\s+(instructions?|prompts?)",
    r"new\s+instructions?:",
    r"system\s*:\s*",
    r"admin\s+mode",
    r"developer\s+mode",
    r"debug\s+mode",
    # Role-playing attacks
    r"you\s+are\s+now",
    r"act\s+as\s+(a|an)\s+\w+",
    r"pretend\s+(to\s+be|you\s+are)",
    r"roleplay\s+as",
    # Escape attempts
    r"<\s*\|.*?\|\s*>",  # Special tokens
    r"\[INST\]",  # Instruction markers
    r"\[/INST\]",
    r"```.*?system.*?```",  # Code blocks with system prompts
    # Data exfiltration attempts
    r"show\s+me\s+(your|the)\s+(prompt|instructions?|system)",
    r"what\s+(are|is)\s+your\s+(instructions?|prompt|rules?)",
    r"repeat\s+(your|the)\s+(instructions?|prompt)",
    # Jailbreak patterns
    r"DAN\s+mode",  # "Do Anything Now"
    r"jailbreak",
    r"unrestricted",
]

# Suspicious keywords that shouldn't appear in tactical data
SUSPICIOUS_KEYWORDS: set[str] = {
    "ignore",
    "disregard",
    "forget",
    "override",
    "bypass",
    "jailbreak",
    "prompt",
    "admin",
    "execute",
    "eval",
    "script",
    "<script>",
    "javascript:",
    "sql",
    "union",
    "select",
    "drop",
    "delete",
    "insert",
    "__import__",
    "exec(",
    "eval(",
    "compile(",
}

# Compiled regex patterns for performance
_COMPILED_PATTERNS: list[re.Pattern[str]] | None = None


def _get_compiled_patterns() -> list[re.Pattern[str]]:
    """Get compiled regex patterns (lazy initialization)."""
    global _COMPILED_PATTERNS
    if _COMPILED_PATTERNS is None:
        _COMPILED_PATTERNS = [
            re.compile(pattern, re.IGNORECASE) for pattern in PROMPT_INJECTION_PATTERNS
        ]
    return _COMPILED_PATTERNS


# =============================================================================
# Internal Validation Functions
# =============================================================================


def _check_prompt_injection(text: str) -> tuple[bool, list[str]]:
    """
    Check for prompt injection patterns in text.

    Args:
        text: Text to scan.

    Returns:
        Tuple of (is_safe, detected_patterns).
    """
    detected: list[str] = []
    text_lower = text.lower()

    # Check regex patterns
    for pattern in _get_compiled_patterns():
        if pattern.search(text_lower):
            detected.append(f"Injection pattern detected: {pattern.pattern[:40]}...")

    # Check suspicious keywords
    for keyword in SUSPICIOUS_KEYWORDS:
        if keyword.lower() in text_lower:
            detected.append(f"Suspicious keyword: '{keyword}'")

    return len(detected) == 0, detected


def _scan_text_fields(
    data: dict[str, Any],
    path: str = "",
) -> tuple[bool, list[str]]:
    """
    Recursively scan all text fields in data for injection attempts.

    Args:
        data: Dictionary to scan.
        path: Current path in nested structure (for error reporting).

    Returns:
        Tuple of (is_safe, issues).
    """
    issues: list[str] = []

    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key

        if isinstance(value, str):
            is_safe, detected = _check_prompt_injection(value)
            if not is_safe:
                issues.extend(f"{current_path}: {d}" for d in detected)

        elif isinstance(value, dict):
            is_safe, nested = _scan_text_fields(value, current_path)
            if not is_safe:
                issues.extend(nested)

        elif isinstance(value, list):
            for i, item in enumerate(value):
                item_path = f"{current_path}[{i}]"
                if isinstance(item, str):
                    is_safe, detected = _check_prompt_injection(item)
                    if not is_safe:
                        issues.extend(f"{item_path}: {d}" for d in detected)
                elif isinstance(item, dict):
                    is_safe, nested = _scan_text_fields(item, item_path)
                    if not is_safe:
                        issues.extend(nested)

    return len(issues) == 0, issues


def _check_coordinate_validity(lat: float, lon: float) -> tuple[bool, str]:
    """
    Validate geographic coordinates.

    Args:
        lat: Latitude value.
        lon: Longitude value.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not isinstance(lat, int | float) or not isinstance(lon, int | float):
        return False, f"Coordinates must be numeric (lat={lat}, lon={lon})"

    if not -90 <= lat <= 90:
        return False, f"Latitude {lat} out of valid range [-90, 90]"

    if not -180 <= lon <= 180:
        return False, f"Longitude {lon} out of valid range [-180, 180]"

    return True, ""


def _scan_coordinates_in_data(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Scan data for coordinate fields and validate them.

    Args:
        data: Data dictionary to scan.

    Returns:
        Tuple of (is_valid, issues).
    """
    issues: list[str] = []

    # Check nested location object
    if "location" in data and isinstance(data["location"], dict):
        loc = data["location"]
        lat = loc.get("lat")
        lon = loc.get("lon")
        if lat is not None and lon is not None:
            is_valid, error = _check_coordinate_validity(lat, lon)
            if not is_valid:
                issues.append(f"location: {error}")

    # Check direct lat/lon fields
    lat = data.get("latitude") or data.get("lat")
    lon = data.get("longitude") or data.get("lon")
    if lat is not None and lon is not None:
        is_valid, error = _check_coordinate_validity(lat, lon)
        if not is_valid:
            issues.append(f"coordinates: {error}")

    # Recursively check nested structures
    for key, value in data.items():
        if key == "location":
            continue

        if isinstance(value, dict):
            is_valid, nested = _scan_coordinates_in_data(value)
            if not is_valid:
                issues.extend(f"{key}.{i}" for i in nested)

        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, dict):
                    is_valid, nested = _scan_coordinates_in_data(item)
                    if not is_valid:
                        issues.extend(f"{key}[{idx}].{i}" for i in nested)

    return len(issues) == 0, issues


def _check_sensor_authorization(
    sensor_id: str,
    sensor_type: str,
    authorized_sensors: dict[str, dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    """
    Validate sensor is authorized and type matches.

    Args:
        sensor_id: Sensor identifier.
        sensor_type: Claimed sensor type.
        authorized_sensors: Optional whitelist of authorized sensors.

    Returns:
        Tuple of (is_authorized, error_message).
    """
    # If no whitelist provided, skip authorization check
    if authorized_sensors is None:
        return True, ""

    if sensor_id not in authorized_sensors:
        return False, f"Unauthorized sensor: {sensor_id}"

    sensor_config = authorized_sensors[sensor_id]
    expected_type = sensor_config.get("sensor_type")

    if expected_type and expected_type != sensor_type:
        return False, f"Sensor type mismatch: expected {expected_type}, got {sensor_type}"

    if not sensor_config.get("enabled", True):
        return False, f"Sensor {sensor_id} is disabled"

    return True, ""


def _check_message_structure(sensor_msg: SensorMessage) -> tuple[bool, str]:
    """
    Validate SensorMessage structure.

    Args:
        sensor_msg: SensorMessage to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    # Validate sensor_type
    if sensor_msg.sensor_type not in SENSOR_TYPES:
        return False, f"Invalid sensor_type: {sensor_msg.sensor_type}"

    # Validate timestamp is not in future (with small tolerance)
    now = datetime.now(UTC)
    if sensor_msg.timestamp > now:
        return False, "Timestamp is in the future"

    # Validate data field
    if isinstance(sensor_msg.data, str):
        if not sensor_msg.data.strip():
            return False, "Data field is empty"
    elif isinstance(sensor_msg.data, dict):
        if not sensor_msg.data:
            return False, "Data field is empty"
    else:
        return False, "Data field must be a dictionary or string"

    return True, ""


# =============================================================================
# Public API
# =============================================================================


def validate_sensor_input(
    sensor_msg: SensorMessage,
    authorized_sensors: dict[str, dict[str, Any]] | None = None,
    strict_mode: bool = True,
) -> ValidationResult:
    """
    Validate incoming sensor message for security threats.

    Performs multi-layer validation:
    1. Sensor authorization (if whitelist provided)
    2. Message structure validation
    3. Prompt injection detection
    4. Coordinate validation

    Args:
        sensor_msg: Sensor message to validate.
        authorized_sensors: Optional whitelist of authorized sensors.
        strict_mode: If True, fail on any security issue.

    Returns:
        ValidationResult with is_valid, error, and warnings.

    Example:
        result = validate_sensor_input(sensor_msg)
        if not result.is_valid:
            logger.error(f"Blocked: {result.error}")
            return

        if result.warnings:
            logger.warning(f"Warnings: {result.warnings}")
    """
    warnings: list[str] = []

    # Check 1: Sensor authorization
    is_authorized, error = _check_sensor_authorization(
        sensor_msg.sensor_id,
        sensor_msg.sensor_type,
        authorized_sensors,
    )
    if not is_authorized:
        return ValidationResult(is_valid=False, error=f"[FIREWALL] {error}")

    # Check 2: Message structure
    is_valid, error = _check_message_structure(sensor_msg)
    if not is_valid:
        return ValidationResult(is_valid=False, error=f"[FIREWALL] Structure: {error}")

    # Check 3: Prompt injection (only for dict data)
    if isinstance(sensor_msg.data, dict):
        is_safe, issues = _scan_text_fields(sensor_msg.data)
        if not is_safe:
            error_msg = "[FIREWALL] Prompt injection detected:\n" + "\n".join(issues)
            if strict_mode:
                return ValidationResult(is_valid=False, error=error_msg)
            warnings.extend(issues)

        # Check 4: Coordinate validation
        is_valid, coord_issues = _scan_coordinates_in_data(sensor_msg.data)
        if not is_valid:
            error_msg = "[FIREWALL] Invalid coordinates:\n" + "\n".join(coord_issues)
            return ValidationResult(is_valid=False, error=error_msg)

    return ValidationResult(is_valid=True, warnings=warnings)


def validate_entity(entity: EntityCOP) -> ValidationResult:
    """
    Validate EntityCOP for security and data integrity.

    Args:
        entity: EntityCOP to validate.

    Returns:
        ValidationResult with is_valid and error.

    Example:
        result = validate_entity(entity)
        if not result:
            raise ValueError(result.error)
    """
    # Check IFF classification
    if entity.classification not in CLASSIFICATIONS:
        return ValidationResult(
            is_valid=False,
            error=f"[FIREWALL] Invalid classification '{entity.classification}'",
        )

    # Check information classification
    if entity.information_classification not in CLASSIFICATION_LEVEL_SET:
        return ValidationResult(
            is_valid=False,
            error=f"[FIREWALL] Invalid info classification '{entity.information_classification}'",
        )

    # Check coordinates
    is_valid, error = _check_coordinate_validity(
        entity.location.lat,
        entity.location.lon,
    )
    if not is_valid:
        return ValidationResult(is_valid=False, error=f"[FIREWALL] {error}")

    # Check confidence range
    if not 0.0 <= entity.confidence <= 1.0:
        return ValidationResult(
            is_valid=False,
            error=f"[FIREWALL] Confidence {entity.confidence} out of range [0.0, 1.0]",
        )

    # Check optional fields
    if entity.speed_kmh is not None and entity.speed_kmh < 0:
        return ValidationResult(
            is_valid=False,
            error=f"[FIREWALL] Speed cannot be negative: {entity.speed_kmh}",
        )

    if entity.heading is not None and not 0 <= entity.heading < 360:
        return ValidationResult(
            is_valid=False,
            error=f"[FIREWALL] Heading {entity.heading} out of range [0, 360)",
        )

    # Check for prompt injection in comments
    if entity.comments:
        is_safe, issues = _check_prompt_injection(entity.comments)
        if not is_safe:
            return ValidationResult(
                is_valid=False,
                error=f"[FIREWALL] Injection in comments: {issues[0]}",
            )

    return ValidationResult(is_valid=True)


def validate_dissemination(
    recipient_access_level: str,
    highest_classification: str,
    entity_ids: list[str],
    is_deception: bool = False,
) -> ValidationResult:
    """
    Validate dissemination decision for security compliance.

    Ensures:
    - Classification level is valid
    - Access level is valid
    - Recipient has sufficient access for data classification
    - Information subset is not empty
    - Special handling for enemy_access (deception operations)

    Args:
        recipient_access_level: Recipient's access level.
        highest_classification: Highest classification in transmission.
        entity_ids: List of entity IDs being shared.
        is_deception: Whether this is disinformation for adversary.

    Returns:
        ValidationResult with is_valid and error.
    """
    # Validate classification level
    if highest_classification not in CLASSIFICATION_LEVEL_SET:
        return ValidationResult(
            is_valid=False,
            error=f"[FIREWALL] Invalid classification level '{highest_classification}'",
        )

    # Validate access level
    if recipient_access_level not in ACCESS_LEVELS:
        return ValidationResult(
            is_valid=False,
            error=f"[FIREWALL] Invalid access level '{recipient_access_level}'",
        )

    # Validate entity_ids not empty
    if not entity_ids:
        return ValidationResult(
            is_valid=False,
            error="[FIREWALL] Entity IDs list cannot be empty",
        )

    # Special case: enemy_access
    if recipient_access_level == "enemy_access":
        if highest_classification != "UNCLASSIFIED" and not is_deception:
            return ValidationResult(
                is_valid=False,
                error=(
                    f"[FIREWALL] CRITICAL: Attempting to send {highest_classification} "
                    f"data to enemy_access WITHOUT deception flag!"
                ),
            )
        return ValidationResult(is_valid=True)

    # Normal access control check (read-down principle)
    if not can_access_classification(recipient_access_level, highest_classification):
        return ValidationResult(
            is_valid=False,
            error=(
                f"[FIREWALL] Access violation: '{recipient_access_level}' "
                f"cannot access '{highest_classification}' data"
            ),
        )

    return ValidationResult(is_valid=True)


def get_firewall_stats() -> dict[str, int]:
    """
    Get statistics about firewall rules.

    Returns:
        Dictionary with counts of patterns and keywords.
    """
    return {
        "injection_patterns": len(PROMPT_INJECTION_PATTERNS),
        "suspicious_keywords": len(SUSPICIOUS_KEYWORDS),
        "sensor_types": len(SENSOR_TYPES),
        "classification_levels": len(CLASSIFICATION_LEVEL_SET),
        "access_levels": len(ACCESS_LEVELS),
    }
