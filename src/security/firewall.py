"""
CopForge Security Firewall.

Multi-layer security validation for incoming sensor data and outgoing transmissions.

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
        logger.error(f"Firewall blocked: {result.error}")

    # Validate entity before COP insertion
    result = validate_entity(entity)
    if not result.is_valid:
        logger.error(f"Entity invalid: {result.error}")
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.core.constants import (
    ACCESS_LEVELS,
    CLASSIFICATION_LEVEL_SET,
    CLASSIFICATIONS,
    SENSOR_TYPES,
    can_access_classification,
)
from src.core.telemetry import get_tracer, traced_operation
from src.models.cop import EntityCOP
from src.models.sensor import SensorMessage

# Get tracer for this module
tracer = get_tracer("copforge.security.firewall")


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class FirewallResult:
    """Result of a firewall validation check."""

    is_valid: bool
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

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
SUSPICIOUS_KEYWORDS: list[str] = [
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
]


# =============================================================================
# Internal Validation Functions
# =============================================================================


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
        authorized_sensors: Dict of authorized sensors (sensor_id -> config).

    Returns:
        Tuple of (is_authorized, error_message).
    """
    # If no whitelist provided, skip authorization check
    if authorized_sensors is None:
        return True, ""

    # Check if sensor is in whitelist
    if sensor_id not in authorized_sensors:
        return False, f"Unauthorized sensor: {sensor_id}"

    # Validate sensor type matches configuration
    sensor_config = authorized_sensors[sensor_id]
    expected_type = sensor_config.get("sensor_type")

    if expected_type and expected_type != sensor_type:
        return False, f"Sensor type mismatch: expected {expected_type}, got {sensor_type}"

    # Check if sensor is enabled
    if not sensor_config.get("enabled", True):
        return False, f"Sensor {sensor_id} is disabled"

    return True, ""


def _check_sensor_message_structure(sensor_msg: SensorMessage) -> tuple[bool, str]:
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

    # Validate data field exists and is dict or str
    if not isinstance(sensor_msg.data, dict | str):
        return False, "Data field must be a dictionary or string"

    # If data is empty, that's suspicious
    if not sensor_msg.data:
        return False, "Data field is empty"

    return True, ""


def _check_coordinate_validity(lat: float, lon: float) -> tuple[bool, str]:
    """
    Validate geographic coordinates are within valid ranges.

    Args:
        lat: Latitude.
        lon: Longitude.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not isinstance(lat, int | float) or not isinstance(lon, int | float):
        return False, f"Coordinates must be numeric (lat={lat}, lon={lon})"

    if not (-90 <= lat <= 90):
        return False, f"Latitude {lat} out of valid range [-90, 90]"

    if not (-180 <= lon <= 180):
        return False, f"Longitude {lon} out of valid range [-180, 180]"

    return True, ""


def _check_prompt_injection(text: str) -> tuple[bool, list[str]]:
    """
    Check for prompt injection patterns in text.

    Args:
        text: Text to scan.

    Returns:
        Tuple of (is_safe, list_of_detected_patterns).
    """
    detected_patterns: list[str] = []
    text_lower = text.lower()

    # Check regex patterns
    for pattern in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            detected_patterns.append(f"Injection pattern: {pattern[:50]}...")

    # Check suspicious keywords
    for keyword in SUSPICIOUS_KEYWORDS:
        if keyword.lower() in text_lower:
            detected_patterns.append(f"Suspicious keyword: '{keyword}'")

    is_safe = len(detected_patterns) == 0
    return is_safe, detected_patterns


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
        Tuple of (is_safe, list_of_issues).
    """
    all_issues: list[str] = []

    for key, value in data.items():
        current_path = f"{path}.{key}" if path else key

        # If value is string, check it
        if isinstance(value, str):
            is_safe, issues = _check_prompt_injection(value)
            if not is_safe:
                for issue in issues:
                    all_issues.append(f"{current_path}: {issue}")

        # If value is dict, recurse
        elif isinstance(value, dict):
            is_safe, issues = _scan_text_fields(value, current_path)
            if not is_safe:
                all_issues.extend(issues)

        # If value is list, check each item
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str):
                    is_safe, issues = _check_prompt_injection(item)
                    if not is_safe:
                        for issue in issues:
                            all_issues.append(f"{current_path}[{i}]: {issue}")
                elif isinstance(item, dict):
                    is_safe, issues = _scan_text_fields(item, f"{current_path}[{i}]")
                    if not is_safe:
                        all_issues.extend(issues)

    is_safe = len(all_issues) == 0
    return is_safe, all_issues


def _scan_coordinates_in_data(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Scan data for coordinate fields and validate them.

    Args:
        data: Data dictionary to scan.

    Returns:
        Tuple of (is_valid, list_of_issues).
    """
    issues: list[str] = []

    # Check top-level coordinates
    if "location" in data and isinstance(data["location"], dict):
        lat = data["location"].get("lat")
        lon = data["location"].get("lon")

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
        if isinstance(value, dict) and key != "location":
            is_valid, nested_issues = _scan_coordinates_in_data(value)
            if not is_valid:
                issues.extend([f"{key}.{issue}" for issue in nested_issues])

        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    is_valid, nested_issues = _scan_coordinates_in_data(item)
                    if not is_valid:
                        issues.extend([f"{key}[{i}].{issue}" for issue in nested_issues])

    is_valid = len(issues) == 0
    return is_valid, issues


def _check_classification_validity(classification: str) -> tuple[bool, str]:
    """
    Validate entity classification (IFF affiliation).

    Args:
        classification: Classification string.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if classification.lower() not in CLASSIFICATIONS:
        return (
            False,
            f"Invalid classification '{classification}'. Must be one of: {CLASSIFICATIONS}",
        )
    return True, ""


def _check_information_classification_validity(level: str) -> tuple[bool, str]:
    """
    Validate security classification level.

    Args:
        level: Classification level string.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if level.upper() not in CLASSIFICATION_LEVEL_SET:
        return (
            False,
            f"Invalid classification level '{level}'. Must be one of: {CLASSIFICATION_LEVEL_SET}",
        )
    return True, ""


def _check_access_level_validity(access_level: str) -> tuple[bool, str]:
    """
    Validate access level.

    Args:
        access_level: Access level string.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if access_level.lower() not in ACCESS_LEVELS:
        return False, f"Invalid access level '{access_level}'. Must be one of: {ACCESS_LEVELS}"
    return True, ""


# =============================================================================
# Main Firewall Functions
# =============================================================================


def validate_sensor_input(
    sensor_msg: SensorMessage,
    authorized_sensors: dict[str, dict[str, Any]] | None = None,
    strict_mode: bool = True,
) -> FirewallResult:
    """
    Validate incoming sensor message for security threats.

    Performs multi-layer validation:
    1. Sensor authorization (if whitelist provided)
    2. Message structure validation
    3. Prompt injection detection
    4. Coordinate validation

    Args:
        sensor_msg: Sensor message to validate.
        authorized_sensors: Dict of authorized sensors (optional whitelist).
        strict_mode: If True, fail on any security issue. If False, add warnings.

    Returns:
        FirewallResult with validation status and details.

    Example:
        >>> result = validate_sensor_input(sensor_msg)
        >>> if not result.is_valid:
        ...     print(f"Blocked: {result.error}")
    """
    with traced_operation(
        tracer,
        "validate_sensor_input",
        {
            "sensor_id": sensor_msg.sensor_id,
            "sensor_type": sensor_msg.sensor_type,
            "strict_mode": strict_mode,
        },
    ) as span:
        warnings: list[str] = []
        details: dict[str, Any] = {
            "sensor_id": sensor_msg.sensor_id,
            "sensor_type": sensor_msg.sensor_type,
            "checks_passed": [],
            "checks_failed": [],
        }

        # Check 1: Sensor authorization
        is_authorized, error = _check_sensor_authorization(
            sensor_msg.sensor_id,
            sensor_msg.sensor_type,
            authorized_sensors,
        )
        if not is_authorized:
            details["checks_failed"].append("sensor_authorization")
            span.set_attribute("firewall.result", "blocked")
            span.set_attribute("firewall.reason", "sensor_authorization")
            return FirewallResult(
                is_valid=False,
                error=f"[FIREWALL] {error}",
                details=details,
            )
        details["checks_passed"].append("sensor_authorization")

        # Check 2: Message structure validation
        is_valid, error = _check_sensor_message_structure(sensor_msg)
        if not is_valid:
            details["checks_failed"].append("message_structure")
            span.set_attribute("firewall.result", "blocked")
            span.set_attribute("firewall.reason", "message_structure")
            return FirewallResult(
                is_valid=False,
                error=f"[FIREWALL] Structure error: {error}",
                details=details,
            )
        details["checks_passed"].append("message_structure")

        # Check 3: Scan all text fields for prompt injection
        if isinstance(sensor_msg.data, dict):
            is_safe, issues = _scan_text_fields(sensor_msg.data)
            if not is_safe:
                error_msg = "[FIREWALL] Prompt injection detected:\n" + "\n".join(issues)
                if strict_mode:
                    details["checks_failed"].append("prompt_injection")
                    details["injection_issues"] = issues
                    span.set_attribute("firewall.result", "blocked")
                    span.set_attribute("firewall.reason", "prompt_injection")
                    return FirewallResult(
                        is_valid=False,
                        error=error_msg,
                        details=details,
                    )
                else:
                    # In non-strict mode, add warning but continue
                    warnings.append(error_msg)
            details["checks_passed"].append("prompt_injection")

            # Check 4: Validate all coordinates in data
            is_valid, issues = _scan_coordinates_in_data(sensor_msg.data)
            if not is_valid:
                error_msg = "[FIREWALL] Invalid coordinates:\n" + "\n".join(issues)
                details["checks_failed"].append("coordinate_validation")
                details["coordinate_issues"] = issues
                span.set_attribute("firewall.result", "blocked")
                span.set_attribute("firewall.reason", "invalid_coordinates")
                return FirewallResult(
                    is_valid=False,
                    error=error_msg,
                    details=details,
                )
            details["checks_passed"].append("coordinate_validation")

        # All checks passed
        span.set_attribute("firewall.result", "passed")
        span.set_attribute("firewall.warnings_count", len(warnings))

        return FirewallResult(
            is_valid=True,
            warnings=warnings,
            details=details,
        )


def validate_entity(entity: EntityCOP) -> FirewallResult:
    """
    Validate EntityCOP for security and data integrity.

    Checks:
    - IFF classification validity
    - Information classification validity
    - Coordinate validity
    - Confidence range
    - Speed and heading ranges
    - Prompt injection in comments

    Args:
        entity: EntityCOP to validate.

    Returns:
        FirewallResult with validation status and details.

    Example:
        >>> result = validate_entity(entity)
        >>> if not result.is_valid:
        ...     print(f"Invalid: {result.error}")
    """
    with traced_operation(
        tracer,
        "validate_entity",
        {
            "entity_id": entity.entity_id,
            "entity_type": entity.entity_type,
        },
    ) as span:
        details: dict[str, Any] = {
            "entity_id": entity.entity_id,
            "entity_type": entity.entity_type,
            "checks_passed": [],
            "checks_failed": [],
        }

        # Check IFF classification
        is_valid, error = _check_classification_validity(entity.classification)
        if not is_valid:
            details["checks_failed"].append("classification")
            span.set_attribute("firewall.result", "invalid")
            return FirewallResult(is_valid=False, error=f"[FIREWALL] {error}", details=details)
        details["checks_passed"].append("classification")

        # Check information classification
        is_valid, error = _check_information_classification_validity(
            entity.information_classification
        )
        if not is_valid:
            details["checks_failed"].append("information_classification")
            span.set_attribute("firewall.result", "invalid")
            return FirewallResult(is_valid=False, error=f"[FIREWALL] {error}", details=details)
        details["checks_passed"].append("information_classification")

        # Check coordinates
        is_valid, error = _check_coordinate_validity(
            entity.location.lat,
            entity.location.lon,
        )
        if not is_valid:
            details["checks_failed"].append("coordinates")
            span.set_attribute("firewall.result", "invalid")
            return FirewallResult(is_valid=False, error=f"[FIREWALL] {error}", details=details)
        details["checks_passed"].append("coordinates")

        # Check confidence range
        if not (0.0 <= entity.confidence <= 1.0):
            details["checks_failed"].append("confidence")
            span.set_attribute("firewall.result", "invalid")
            return FirewallResult(
                is_valid=False,
                error=f"[FIREWALL] Confidence {entity.confidence} out of range [0.0, 1.0]",
                details=details,
            )
        details["checks_passed"].append("confidence")

        # Check optional fields
        if entity.speed_kmh is not None and entity.speed_kmh < 0:
            details["checks_failed"].append("speed")
            span.set_attribute("firewall.result", "invalid")
            return FirewallResult(
                is_valid=False,
                error=f"[FIREWALL] Speed cannot be negative: {entity.speed_kmh}",
                details=details,
            )
        details["checks_passed"].append("speed")

        if entity.heading is not None and not (0 <= entity.heading < 360):
            details["checks_failed"].append("heading")
            span.set_attribute("firewall.result", "invalid")
            return FirewallResult(
                is_valid=False,
                error=f"[FIREWALL] Heading {entity.heading} out of range [0, 360)",
                details=details,
            )
        details["checks_passed"].append("heading")

        # Check for prompt injection in comments
        if entity.comments:
            is_safe, issues = _check_prompt_injection(entity.comments)
            if not is_safe:
                details["checks_failed"].append("comments_injection")
                span.set_attribute("firewall.result", "invalid")
                return FirewallResult(
                    is_valid=False,
                    error=f"[FIREWALL] Injection in comments: {issues[0]}",
                    details=details,
                )
        details["checks_passed"].append("comments")

        span.set_attribute("firewall.result", "valid")
        return FirewallResult(is_valid=True, details=details)


def validate_dissemination(
    recipient_id: str,
    recipient_access_level: str,
    highest_classification_sent: str,
    information_subset: list[str],
    is_deception: bool = False,
) -> FirewallResult:
    """
    Validate dissemination decision for security compliance.

    Ensures:
    - Classification level is valid
    - Access level is valid
    - Recipient has sufficient access level for data classification
    - Information subset is not empty
    - Special handling for enemy_access (honeypot/deception)

    Args:
        recipient_id: Recipient identifier.
        recipient_access_level: Recipient's access level.
        highest_classification_sent: Highest classification in transmission.
        information_subset: List of entity IDs being shared.
        is_deception: Whether this is disinformation for enemy.

    Returns:
        FirewallResult with validation status and details.

    Example:
        >>> result = validate_dissemination(
        ...     recipient_id="allied_unit",
        ...     recipient_access_level="secret_access",
        ...     highest_classification_sent="CONFIDENTIAL",
        ...     information_subset=["entity_001"],
        ... )
    """
    with traced_operation(
        tracer,
        "validate_dissemination",
        {
            "recipient_id": recipient_id,
            "access_level": recipient_access_level,
            "classification": highest_classification_sent,
            "is_deception": is_deception,
        },
    ) as span:
        details: dict[str, Any] = {
            "recipient_id": recipient_id,
            "access_level": recipient_access_level,
            "classification": highest_classification_sent,
            "entity_count": len(information_subset),
        }

        # Validate classification level
        is_valid, error = _check_information_classification_validity(highest_classification_sent)
        if not is_valid:
            span.set_attribute("firewall.result", "invalid")
            return FirewallResult(is_valid=False, error=f"[FIREWALL] {error}", details=details)

        # Validate access level
        is_valid, error = _check_access_level_validity(recipient_access_level)
        if not is_valid:
            span.set_attribute("firewall.result", "invalid")
            return FirewallResult(is_valid=False, error=f"[FIREWALL] {error}", details=details)

        # Special case: enemy_access
        if recipient_access_level.lower() == "enemy_access":
            # Enemy must ONLY receive UNCLASSIFIED data (unless deception)
            if highest_classification_sent.upper() != "UNCLASSIFIED":
                if not is_deception:
                    span.set_attribute("firewall.result", "blocked")
                    span.set_attribute("firewall.reason", "enemy_data_leak")
                    return FirewallResult(
                        is_valid=False,
                        error=(
                            f"[FIREWALL] CRITICAL: Attempting to send {highest_classification_sent} "
                            f"data to enemy_access recipient WITHOUT deception flag! "
                            f"This could be a data leak!"
                        ),
                        details=details,
                    )
                # If is_deception=True, this is intentional disinformation
                details["deception_operation"] = True

            # Validate information subset for enemy
            if not information_subset:
                span.set_attribute("firewall.result", "invalid")
                return FirewallResult(
                    is_valid=False,
                    error="[FIREWALL] Information subset cannot be empty",
                    details=details,
                )

            span.set_attribute("firewall.result", "passed")
            return FirewallResult(is_valid=True, details=details)

        # Normal access control check (read-down principle)
        if not can_access_classification(recipient_access_level, highest_classification_sent):
            span.set_attribute("firewall.result", "blocked")
            span.set_attribute("firewall.reason", "access_control_violation")
            return FirewallResult(
                is_valid=False,
                error=(
                    f"[FIREWALL] Access control violation: "
                    f"Recipient with '{recipient_access_level}' cannot access "
                    f"'{highest_classification_sent}' data"
                ),
                details=details,
            )

        # Validate information subset
        if not information_subset:
            span.set_attribute("firewall.result", "invalid")
            return FirewallResult(
                is_valid=False,
                error="[FIREWALL] Information subset cannot be empty",
                details=details,
            )

        span.set_attribute("firewall.result", "passed")
        return FirewallResult(is_valid=True, details=details)


# =============================================================================
# Utility Functions
# =============================================================================


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
