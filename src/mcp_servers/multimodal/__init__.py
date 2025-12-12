"""
MCP Server: Multimodal - Tools for processing audio, images, and documents.
"""

from src.mcp_servers.multimodal.audio_tools import (
    is_audio_file,
    transcribe_audio,
    transcribe_audio_simple,
    transcribe_audio_with_speakers,
    validate_audio_file,
)
from src.mcp_servers.multimodal.document_tools import (
    get_document_info,
    is_document_file,
    process_document,
    validate_document_file,
)
from src.mcp_servers.multimodal.image_tools import (
    analyze_image,
    is_image_file,
    validate_image_file,
)
from src.mcp_servers.multimodal.server import app, main

__all__ = [
    "app",
    "main",
    "transcribe_audio",
    "transcribe_audio_simple",
    "transcribe_audio_with_speakers",
    "is_audio_file",
    "validate_audio_file",
    "analyze_image",
    "is_image_file",
    "validate_image_file",
    "process_document",
    "get_document_info",
    "is_document_file",
    "validate_document_file",
]
