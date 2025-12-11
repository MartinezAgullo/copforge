"""
Parsers module for CopForge.

Provides format-specific parsers for converting sensor data into EntityCOP objects.

Available parsers:
- ASTERIXParser: ASTERIX radar format
- DroneParser: Drone telemetry and imagery
- RadioParser: Radio intercept metadata
- ManualParser: Human-generated reports

Usage:
    from src.parsers import get_parser_factory

    factory = get_parser_factory()
    result = factory.parse(sensor_msg)

    if result.success:
        for entity in result.entities:
            print(f"Created: {entity.entity_id}")
    else:
        print(f"Error: {result.error}")
"""

from src.parsers.asterix_parser import ASTERIXParser
from src.parsers.base_parser import BaseParser
from src.parsers.drone_parser import DroneParser
from src.parsers.manual_parser import ManualParser
from src.parsers.parser_factory import ParseResult, ParserFactory, get_parser_factory
from src.parsers.radio_parser import RadioParser

__all__ = [
    # Base
    "BaseParser",
    # Parsers
    "ASTERIXParser",
    "DroneParser",
    "RadioParser",
    "ManualParser",
    # Factory
    "ParserFactory",
    "ParseResult",
    "get_parser_factory",
]
