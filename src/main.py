"""
CopForge Main Entry Point.

End-to-end pipeline for sensor data ingestion:
1. Receive SensorMessage
2. Validate through Firewall
3. Parse to EntityCOP via ParserFactory
4. Send to COP Fusion MCP Server
5. Sync to mapa-puntos-interes

Usage:
    # Run with sample data
    uv run python -m src.main

    # Or import and use programmatically
    from src.main import ingest_sensor_message
    result = await ingest_sensor_message(sensor_msg)
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from src.core.telemetry import get_tracer, setup_telemetry, traced_operation
from src.mcp_client import CopFusionClient, MCPClientError
from src.models.cop import EntityCOP
from src.models.sensor import SensorMessage
from src.parsers import ParseResult, get_parser_factory
from src.security.firewall import FirewallResult, validate_entity, validate_sensor_input

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
tracer = get_tracer("copforge.main")


# =============================================================================
# Result Types
# =============================================================================


class IngestResult:
    """Result of ingesting a sensor message."""

    def __init__(
        self,
        success: bool,
        entities: list[EntityCOP] | None = None,
        error: str = "",
        stage: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.success = success
        self.entities = entities or []
        self.error = error
        self.stage = stage  # firewall, parser, validation, cop_fusion
        self.details = details or {}

    def __bool__(self) -> bool:
        return self.success

    def __repr__(self) -> str:
        if self.success:
            return f"IngestResult(success=True, entities={len(self.entities)})"
        return f"IngestResult(success=False, stage={self.stage}, error={self.error[:50]}...)"


# =============================================================================
# Ingest Pipeline
# =============================================================================


async def ingest_sensor_message(
    sensor_msg: SensorMessage,
    client: CopFusionClient,
    authorized_sensors: dict[str, dict[str, Any]] | None = None,
    strict_mode: bool = True,
) -> IngestResult:
    """
    Process a single sensor message through the full pipeline.

    Pipeline stages:
    1. Firewall validation
    2. Parser extraction
    3. Entity validation
    4. COP Fusion update

    Args:
        sensor_msg: Raw sensor message to process.
        client: Connected COP Fusion MCP client.
        authorized_sensors: Optional whitelist of authorized sensors.
        strict_mode: If True, fail on any security issue.

    Returns:
        IngestResult with success status and processed entities.
    """
    with traced_operation(
        tracer,
        "ingest_sensor_message",
        {
            "sensor_id": sensor_msg.sensor_id,
            "sensor_type": sensor_msg.sensor_type,
        },
    ) as span:
        logger.info(f"Ingesting message from {sensor_msg.sensor_id} ({sensor_msg.sensor_type})")

        # Stage 1: Firewall validation
        with traced_operation(tracer, "firewall_validation") as fw_span:
            firewall_result: FirewallResult = validate_sensor_input(
                sensor_msg,
                authorized_sensors=authorized_sensors,
                strict_mode=strict_mode,
            )
            fw_span.set_attribute("firewall.passed", firewall_result.is_valid)

        if not firewall_result.is_valid:
            logger.warning(f"Firewall blocked: {firewall_result.error}")
            span.set_attribute("ingest.stage_failed", "firewall")
            return IngestResult(
                success=False,
                stage="firewall",
                error=firewall_result.error,
                details=firewall_result.details,
            )

        if firewall_result.warnings:
            for warning in firewall_result.warnings:
                logger.warning(f"Firewall warning: {warning}")

        logger.debug("Firewall passed")

        # Stage 2: Parse sensor message to entities
        with traced_operation(tracer, "parser_extraction") as parser_span:
            parser_factory = get_parser_factory()
            parse_result: ParseResult = parser_factory.parse(sensor_msg)
            parser_span.set_attribute("parser.success", parse_result.success)
            parser_span.set_attribute("parser.name", parse_result.parser_used)

        if not parse_result.success:
            logger.error(f"Parser failed: {parse_result.error}")
            span.set_attribute("ingest.stage_failed", "parser")
            return IngestResult(
                success=False,
                stage="parser",
                error=parse_result.error,
                details=parse_result.details,
            )

        logger.info(
            f"Parsed {len(parse_result.entities)} entities using {parse_result.parser_used}"
        )

        # Stage 3: Validate each entity
        with traced_operation(tracer, "entity_validation") as val_span:
            valid_entities: list[EntityCOP] = []
            validation_errors: list[str] = []

            for entity in parse_result.entities:
                entity_result: FirewallResult = validate_entity(entity)
                if entity_result.is_valid:
                    valid_entities.append(entity)
                else:
                    validation_errors.append(f"{entity.entity_id}: {entity_result.error}")
                    logger.warning(f"Entity validation failed: {entity_result.error}")

            val_span.set_attribute("validation.valid_count", len(valid_entities))
            val_span.set_attribute("validation.error_count", len(validation_errors))

        if not valid_entities:
            span.set_attribute("ingest.stage_failed", "validation")
            return IngestResult(
                success=False,
                stage="validation",
                error=f"All entities failed validation: {validation_errors}",
                details={"validation_errors": validation_errors},
            )

        logger.info(f"Validated {len(valid_entities)}/{len(parse_result.entities)} entities")

        # Stage 4: Update COP via MCP
        try:
            with traced_operation(tracer, "cop_fusion_update") as cop_span:
                entities_data = [e.model_dump_json_safe() for e in valid_entities]
                cop_result = await client.update_cop(entities_data)
                cop_span.set_attribute("cop.added", cop_result.get("added", 0))
                cop_span.set_attribute("cop.updated", cop_result.get("updated", 0))

            if "error" in cop_result:
                span.set_attribute("ingest.stage_failed", "cop_fusion")
                return IngestResult(
                    success=False,
                    stage="cop_fusion",
                    error=cop_result["error"],
                    details=cop_result,
                )

            logger.info(
                f"COP updated: {cop_result.get('added', 0)} added, "
                f"{cop_result.get('updated', 0)} updated"
            )

            span.set_attribute("ingest.success", True)
            span.set_attribute("ingest.entities_count", len(valid_entities))

            return IngestResult(
                success=True,
                entities=valid_entities,
                details={
                    "firewall": firewall_result.details,
                    "parser": parse_result.details,
                    "cop_update": cop_result,
                    "validation_errors": validation_errors,
                },
            )

        except MCPClientError as e:
            logger.error(f"MCP client error: {e}")
            span.set_attribute("ingest.stage_failed", "cop_fusion")
            span.set_attribute("ingest.error", str(e))
            return IngestResult(
                success=False,
                stage="cop_fusion",
                error=str(e),
            )


async def ingest_batch(
    messages: list[SensorMessage],
    client: CopFusionClient,
    authorized_sensors: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Process a batch of sensor messages.

    Args:
        messages: List of sensor messages.
        client: Connected COP Fusion MCP client.
        authorized_sensors: Optional whitelist.

    Returns:
        Batch statistics.
    """
    with traced_operation(tracer, "ingest_batch", {"batch_size": len(messages)}) as span:
        total = len(messages)
        success = 0
        failed = 0
        entities_created = 0
        errors: list[dict[str, str]] = []

        for msg in messages:
            result = await ingest_sensor_message(msg, client, authorized_sensors)
            if result.success:
                success += 1
                entities_created += len(result.entities)
            else:
                failed += 1
                errors.append(
                    {"sensor_id": msg.sensor_id, "stage": result.stage, "error": result.error}
                )

        span.set_attribute("batch.success", success)
        span.set_attribute("batch.failed", failed)
        span.set_attribute("batch.entities_created", entities_created)

        return {
            "total": total,
            "success": success,
            "failed": failed,
            "entities_created": entities_created,
            "errors": errors,
        }


# =============================================================================
# Demo / Test Data
# =============================================================================


def create_sample_radar_message() -> SensorMessage:
    """Create a sample ASTERIX radar message for testing."""
    return SensorMessage(
        sensor_id="radar_01",
        sensor_type="radar",
        timestamp=datetime.now(UTC),
        data={
            "format": "asterix",
            "system_id": "ES_RAD_101",
            "is_simulated": True,
            "tracks": [
                {
                    "track_id": "T001",
                    "location": {"lat": 39.4699, "lon": -0.3763},
                    "altitude_m": 5000,
                    "speed_kmh": 450,
                    "heading": 270,
                    "classification": "unknown",
                },
                {
                    "track_id": "T002",
                    "location": {"lat": 39.5100, "lon": -0.4200},
                    "altitude_m": 3500,
                    "speed_kmh": 380,
                    "heading": 90,
                    "classification": "friendly",
                },
            ],
        },
    )


def create_sample_drone_message() -> SensorMessage:
    """Create a sample drone telemetry message for testing."""
    return SensorMessage(
        sensor_id="drone_alpha",
        sensor_type="drone",
        timestamp=datetime.now(UTC),
        data={
            "drone_id": "DRONE_ALPHA_01",
            "latitude": 39.4762,
            "longitude": -0.3747,
            "altitude_m_agl": 120,
            "altitude_m_msl": 145,
            "heading": 45,
            "ground_speed_kmh": 35,
            "battery_percent": 78,
            "flight_mode": "auto",
        },
    )


def create_sample_manual_report() -> SensorMessage:
    """Create a sample manual SPOTREP for testing."""
    return SensorMessage(
        sensor_id="operator_01",
        sensor_type="manual",
        timestamp=datetime.now(UTC),
        data={
            "report_id": "SPOTREP_001",
            "report_type": "SPOTREP",
            "priority": "high",
            "operator_name": "Cpt. Martinez",
            "content": "Visual confirmation: Two military helicopters heading NE",
            "latitude": 39.48,
            "longitude": -0.35,
        },
    )


def create_sample_image_message(image_path: str = "data/drone/IMG_001.jpg") -> SensorMessage:
    """
    Create a sample drone message with image reference for multimodal processing.

    Args:
        image_path: Path to the image file to be analyzed.

    Returns:
        SensorMessage with image_link for multimodal processing.
    """
    return SensorMessage(
        sensor_id="drone_bravo",
        sensor_type="drone",
        timestamp=datetime.now(UTC),
        data={
            "drone_id": "DRONE_BRAVO_01",
            "latitude": 39.4850,
            "longitude": -0.3600,
            "altitude_m_agl": 150,
            "altitude_m_msl": 175,
            "heading": 120,
            "ground_speed_kmh": 0,  # Hovering
            "battery_percent": 65,
            "flight_mode": "loiter",
            "camera_heading": 180,
            "image_link": image_path,  # Path to image for multimodal processing
        },
        file_references={
            "image": image_path,
        },
        metadata={
            "capture_mode": "manual",
            "resolution": "4K",
            "analysis_requested": "asset_detection",
        },
    )


def create_sample_audio_message(audio_path: str = "data/radio/intercept_001.mp3") -> SensorMessage:
    """
    Create a sample radio intercept message with audio reference for transcription.

    Args:
        audio_path: Path to the audio file to be transcribed.

    Returns:
        SensorMessage with audio_path for multimodal processing.
    """
    return SensorMessage(
        sensor_id="radio_station_01",
        sensor_type="radio",
        timestamp=datetime.now(UTC),
        data={
            "station_id": "INTERCEPT_CHARLIE_01",
            "frequency_mhz": 145.500,
            "bandwidth_khz": 12.5,
            "modulation_type": "FM",
            "channel": "tactical_alpha",
            "duration_sec": 32.5,
            "signal_strength": -68,
            "audio_path": audio_path,  # Path to audio for transcription
        },
        file_references={
            "audio": audio_path,
        },
        metadata={
            "transcription_requested": True,
            "language_hint": "es",  # Spanish
            "diarization_requested": True,
        },
    )


# =============================================================================
# Main Entry Point
# =============================================================================


async def main() -> None:
    """Run the demo pipeline with sample data."""
    # Initialize telemetry
    telemetry_components = setup_telemetry()

    logger.info("=" * 60)
    logger.info("CopForge - Sensor Ingestion Pipeline Demo")
    logger.info("=" * 60)
    logger.info(
        f"Telemetry: LangSmith={telemetry_components['langsmith_enabled']}, "
        f"OTel={telemetry_components['otel_provider'] is not None}"
    )

    # Create sample messages
    sample_messages = [
        create_sample_radar_message(),
        create_sample_drone_message(),
        create_sample_manual_report(),
    ]

    logger.info(f"Created {len(sample_messages)} sample messages")

    # Connect to COP Fusion MCP Server
    async with CopFusionClient() as client:
        # Check mapa connection
        mapa_status = await client.check_mapa_connection()
        logger.info(f"Mapa connection: {mapa_status}")

        # List available tools
        tools = await client.list_tools()
        logger.info(f"Available MCP tools: {tools}")

        # Process each message
        logger.info("-" * 60)
        logger.info("Processing sensor messages...")
        logger.info("-" * 60)

        batch_result = await ingest_batch(sample_messages, client)

        logger.info("-" * 60)
        logger.info("Batch Results:")
        logger.info(f"  Total messages: {batch_result['total']}")
        logger.info(f"  Successful: {batch_result['success']}")
        logger.info(f"  Failed: {batch_result['failed']}")
        logger.info(f"  Entities created: {batch_result['entities_created']}")

        if batch_result["errors"]:
            logger.warning("Errors:")
            for err in batch_result["errors"]:
                logger.warning(f"  - {err['sensor_id']}: {err['error'][:80]}")

        # Get final COP stats
        logger.info("-" * 60)
        logger.info("Final COP Statistics:")
        stats = await client.get_cop_stats()
        logger.info(f"  Total entities: {stats.get('total_entities', 0)}")
        logger.info(f"  By type: {stats.get('by_type', {})}")
        logger.info(f"  By classification: {stats.get('by_classification', {})}")
        logger.info(f"  Mapa connected: {stats.get('mapa_connected', False)}")

        # Query some entities
        logger.info("-" * 60)
        logger.info("Querying COP...")
        query_result = await client.query_cop(limit=10)
        logger.info(f"  Found {query_result.get('count', 0)} entities")

        # Show first entity
        entities = query_result.get("entities", [])
        if entities:
            first = entities[0]
            logger.info(f"  First entity: {first.get('entity_id')} ({first.get('entity_type')})")

    logger.info("=" * 60)
    logger.info("Demo completed successfully!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
