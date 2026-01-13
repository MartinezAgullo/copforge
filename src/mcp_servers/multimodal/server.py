"""
MCP Server: Multimodal - Tools for processing audio, images, and documents.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.core.telemetry import get_tracer, traced_operation
from src.mcp_servers.multimodal.audio_tools import transcribe_audio
from src.mcp_servers.multimodal.document_tools import process_document
from src.mcp_servers.multimodal.image_tools import analyze_image

logger = logging.getLogger(__name__)
tracer = get_tracer("copforge.mcp.multimodal")


@asynccontextmanager
async def lifespan(_server: Server) -> AsyncIterator[None]:
    """Manage server lifecycle."""
    logger.info("Multimodal MCP Server starting...")
    yield
    logger.info("Multimodal MCP Server shutting down...")


app = Server("multimodal")

ListToolsHandler = Callable[[], Awaitable[list[Tool]]]
CallToolHandler = Callable[[str, dict[str, Any]], Awaitable[list[TextContent]]]

_list_tools = cast(Callable[[ListToolsHandler], ListToolsHandler], app.list_tools())
_call_tool = cast(Callable[[CallToolHandler], CallToolHandler], app.call_tool())

TOOLS = [
    Tool(
        name="transcribe_audio",
        description="""Transcribe audio file to text using Whisper.

Supports speaker diarization (identifies different speakers).
Supported formats: mp3, wav, m4a, flac, ogg, aac, wma

Parameters:
- audio_path: Path to audio file (required)
- enable_diarization: Use speaker identification (default: true)
- num_speakers: Expected number of speakers (null = auto-detect)
- language: ISO language code (null = auto-detect)

Returns: Transcription text with speaker labels if diarization enabled.""",
        inputSchema={
            "type": "object",
            "properties": {
                "audio_path": {"type": "string", "description": "Path to audio file"},
                "enable_diarization": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable speaker diarization",
                },
                "num_speakers": {
                    "type": ["integer", "null"],
                    "default": None,
                    "description": "Expected number of speakers",
                },
                "language": {
                    "type": ["string", "null"],
                    "default": None,
                    "description": "ISO language code",
                },
            },
            "required": ["audio_path"],
        },
    ),
    Tool(
        name="analyze_image",
        description="""Analyze image using Vision Language Model (VLM).

Analysis types:
- general: Full tactical assessment (assets, personnel, terrain, threats)
- asset_detection: Detect military vehicles, aircraft, equipment
- terrain: Terrain and geographic analysis
- damage: Damage assessment
- custom: Use custom_prompt

Supported formats: jpg, jpeg, png, gif, bmp, webp, tiff

Parameters:
- image_path: Path to image file (required)
- analysis_type: Type of analysis (default: "general")
- custom_prompt: Custom prompt (required if analysis_type="custom")
- model: VLM model to use (default: "gpt-4o")

Returns: Detailed analysis based on analysis type.""",
        inputSchema={
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Path to image file"},
                "analysis_type": {
                    "type": "string",
                    "enum": ["general", "asset_detection", "terrain", "damage", "custom"],
                    "default": "general",
                    "description": "Type of analysis to perform",
                },
                "custom_prompt": {
                    "type": ["string", "null"],
                    "default": None,
                    "description": "Custom analysis prompt",
                },
                "model": {
                    "type": "string",
                    "default": "gpt-4o",
                    "description": "VLM model to use",
                },
            },
            "required": ["image_path"],
        },
    ),
    Tool(
        name="process_document",
        description="""Extract text from document file.

Supported formats: pdf, txt, docx

Features:
- PDF: Page-by-page text extraction
- DOCX: Paragraphs and tables extraction
- TXT: Multi-encoding fallback

Parameters:
- document_path: Path to document file (required)
- max_lines: Maximum lines to extract (default: 1000)

Returns: Extracted text content.""",
        inputSchema={
            "type": "object",
            "properties": {
                "document_path": {"type": "string", "description": "Path to document file"},
                "max_lines": {
                    "type": ["integer", "null"],
                    "default": 1000,
                    "description": "Maximum lines to extract",
                },
            },
            "required": ["document_path"],
        },
    ),
]


@_list_tools
async def list_tools() -> list[Tool]:
    """List available tools."""
    return TOOLS


@_call_tool
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool invocations."""
    with traced_operation(tracer, f"mcp_tool_{name}", {"tool": name}) as span:
        try:
            result: dict[str, Any]

            if name == "transcribe_audio":
                result = transcribe_audio(
                    audio_path=arguments["audio_path"],
                    enable_diarization=arguments.get("enable_diarization", True),
                    num_speakers=arguments.get("num_speakers"),
                    language=arguments.get("language"),
                )

            elif name == "analyze_image":
                result = analyze_image(
                    image_path=arguments["image_path"],
                    analysis_type=arguments.get("analysis_type", "general"),
                    custom_prompt=arguments.get("custom_prompt"),
                    model=arguments.get("model", "gpt-4o"),
                )

            elif name == "process_document":
                result = process_document(
                    document_path=arguments["document_path"],
                    max_lines=arguments.get("max_lines", 1000),
                )

            else:
                result = {"success": False, "error": f"Unknown tool: {name}"}

            span.set_attribute("tool.success", result.get("success", False))

            # Format output for LLM consumption
            if result.get("success"):
                output = _format_success_output(name, result)
            else:
                output = _format_error_output(name, result)

            return [TextContent(type="text", text=output)]

        except Exception as e:
            logger.exception(f"Error in tool {name}")
            span.set_attribute("tool.error", str(e))
            return [TextContent(type="text", text=f"Error: {e!s}")]


def _format_success_output(tool_name: str, result: dict[str, Any]) -> str:
    """Format successful result for LLM consumption."""
    if tool_name == "transcribe_audio":
        header = f"""AUDIO TRANSCRIPTION REPORT
==========================
File: {result.get("file_name", "unknown")}
Duration: {result.get("duration", 0):.1f} seconds
Language: {result.get("language", "unknown")}
Speakers: {result.get("num_speakers", 1)} detected
Status: SUCCESS

TRANSCRIPTION:
--------------
"""
        return cast(str, header + result.get("transcription", "") + "\n==========================")

    elif tool_name == "analyze_image":
        header = f"""IMAGE ANALYSIS REPORT
=====================
File: {result.get("file_name", "unknown")}
Analysis Type: {result.get("analysis_type", "unknown")}
Model: {result.get("model_used", "unknown")}
Status: SUCCESS

ANALYSIS:
---------
"""
        return cast(str, header + result.get("analysis", "") + "\n=====================")

    elif tool_name == "process_document":
        header = f"""DOCUMENT EXTRACTION REPORT
==========================
File: {result.get("file_name", "unknown")}
Format: {result.get("format", "unknown").upper()}
Lines extracted: {result.get("num_lines", 0)}
Status: SUCCESS

CONTENT:
--------
"""
        return cast(str, header + result.get("text", "") + "\n==========================")

    return str(result)


def _format_error_output(tool_name: str, result: dict[str, Any]) -> str:
    """Format error result for LLM consumption."""
    report_type = {
        "transcribe_audio": "AUDIO TRANSCRIPTION REPORT",
        "analyze_image": "IMAGE ANALYSIS REPORT",
        "process_document": "DOCUMENT EXTRACTION REPORT",
    }.get(tool_name, "REPORT")

    return f"""{report_type}
{"=" * len(report_type)}
Status: FAILED

ERROR: {result.get("error", "Unknown error")}
{"=" * len(report_type)}
"""


async def main() -> None:
    """Run the MCP server."""
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Multimodal MCP Server...")

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
