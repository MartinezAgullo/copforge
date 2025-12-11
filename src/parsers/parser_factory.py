"""
Parser Factory for CopForge.

Factory for creating appropriate parsers based on sensor message format.
Uses the Strategy pattern to select the right parser for each message type.
"""

from dataclasses import dataclass, field
from typing import Any

from src.core.telemetry import get_tracer, traced_operation
from src.models.cop import EntityCOP
from src.models.sensor import SensorMessage
from src.parsers.asterix_parser import ASTERIXParser
from src.parsers.base_parser import BaseParser
from src.parsers.drone_parser import DroneParser
from src.parsers.manual_parser import ManualParser
from src.parsers.radio_parser import RadioParser

# Get tracer for this module
tracer = get_tracer("copforge.parsers.factory")


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class ParseResult:
    """Result of a parsing operation."""

    success: bool
    entities: list[EntityCOP] = field(default_factory=list)
    error: str = ""
    parser_used: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        """Allow using result in boolean context."""
        return self.success


# =============================================================================
# Parser Factory
# =============================================================================


class ParserFactory:
    """
    Factory for selecting and executing appropriate parser for sensor messages.

    Uses the Strategy pattern to select the right parser based on message type.
    Parsers are tried in order until one accepts the message.

    Example:
        >>> factory = ParserFactory()
        >>> result = factory.parse(sensor_msg)
        >>> if result.success:
        ...     for entity in result.entities:
        ...         print(entity.entity_id)
    """

    def __init__(self) -> None:
        """Initialize parser factory with all available parsers."""
        self.parsers: list[BaseParser] = [
            ASTERIXParser(),
            DroneParser(),
            RadioParser(),
            ManualParser(),
        ]

    def get_parser(self, sensor_msg: SensorMessage) -> BaseParser | None:
        """
        Get appropriate parser for sensor message.

        Args:
            sensor_msg: Sensor message to parse.

        Returns:
            Parser instance that can handle this format, or None if no parser found.
        """
        for parser in self.parsers:
            if parser.can_parse(sensor_msg):
                return parser
        return None

    def parse(self, sensor_msg: SensorMessage) -> ParseResult:
        """
        Parse sensor message using appropriate parser.

        Args:
            sensor_msg: Sensor message to parse.

        Returns:
            ParseResult with success status, entities, and details.
        """
        with traced_operation(
            tracer,
            "parse_sensor_message",
            {
                "sensor_id": sensor_msg.sensor_id,
                "sensor_type": sensor_msg.sensor_type,
            },
        ) as span:
            # Find appropriate parser
            parser = self.get_parser(sensor_msg)

            if parser is None:
                span.set_attribute("parser.found", False)
                return ParseResult(
                    success=False,
                    error=f"No parser found for sensor type '{sensor_msg.sensor_type}'",
                    details={"sensor_type": sensor_msg.sensor_type},
                )

            parser_name = parser.__class__.__name__
            span.set_attribute("parser.name", parser_name)
            span.set_attribute("parser.found", True)

            # Validate message structure
            is_valid, error = parser.validate(sensor_msg)
            if not is_valid:
                span.set_attribute("validation.passed", False)
                return ParseResult(
                    success=False,
                    error=f"Validation failed: {error}",
                    parser_used=parser_name,
                    details={"validation_error": error},
                )

            span.set_attribute("validation.passed", True)

            # Parse message
            try:
                entities = parser.parse(sensor_msg)
                span.set_attribute("entities.count", len(entities))

                return ParseResult(
                    success=True,
                    entities=entities,
                    parser_used=parser_name,
                    details={
                        "entity_count": len(entities),
                        "entity_ids": [e.entity_id for e in entities],
                    },
                )

            except Exception as e:
                span.set_attribute("parse.error", str(e))
                return ParseResult(
                    success=False,
                    error=f"Parsing failed: {str(e)}",
                    parser_used=parser_name,
                    details={"exception": str(e)},
                )

    def register_parser(self, parser: BaseParser) -> None:
        """
        Register a new parser.

        Args:
            parser: Parser instance to register.
        """
        self.parsers.append(parser)

    def list_parsers(self) -> list[str]:
        """
        List all registered parser names.

        Returns:
            List of parser class names.
        """
        return [p.__class__.__name__ for p in self.parsers]


# =============================================================================
# Global Factory Instance (Singleton)
# =============================================================================

_parser_factory: ParserFactory | None = None


def get_parser_factory() -> ParserFactory:
    """
    Get global parser factory instance (singleton).

    Returns:
        ParserFactory instance.

    Example:
        >>> factory = get_parser_factory()
        >>> result = factory.parse(sensor_msg)
    """
    global _parser_factory

    if _parser_factory is None:
        _parser_factory = ParserFactory()

    return _parser_factory
