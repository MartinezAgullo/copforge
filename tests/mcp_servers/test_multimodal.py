"""
Tests for MCP Server: Multimodal

These tests cover validation and utility functions.
Full integration tests require external dependencies (Whisper, VLM APIs).
"""

import os
import tempfile

from src.mcp_servers.multimodal.audio_tools import is_audio_file, validate_audio_file
from src.mcp_servers.multimodal.document_tools import (
    clean_extracted_text,
    is_document_file,
    validate_document_file,
)
from src.mcp_servers.multimodal.image_tools import (
    get_image_mime_type,
    is_image_file,
    validate_image_file,
)

# =============================================================================
# Audio Tools Tests
# =============================================================================


class TestAudioValidation:
    """Tests for audio file validation."""

    def test_is_audio_file_mp3(self) -> None:
        """MP3 should be recognized as audio."""
        assert is_audio_file("test.mp3") is True

    def test_is_audio_file_wav(self) -> None:
        """WAV should be recognized as audio."""
        assert is_audio_file("test.wav") is True

    def test_is_audio_file_flac(self) -> None:
        """FLAC should be recognized as audio."""
        assert is_audio_file("test.flac") is True

    def test_is_audio_file_txt(self) -> None:
        """TXT should not be recognized as audio."""
        assert is_audio_file("test.txt") is False

    def test_is_audio_file_png(self) -> None:
        """PNG should not be recognized as audio."""
        assert is_audio_file("test.png") is False

    def test_validate_audio_file_not_found(self) -> None:
        """Validation should fail for non-existent file."""
        is_valid, error = validate_audio_file("/nonexistent/file.mp3")
        assert is_valid is False
        assert "not found" in error.lower()

    def test_validate_audio_file_unsupported_format(self) -> None:
        """Validation should fail for unsupported format."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            is_valid, error = validate_audio_file(temp_path)
            assert is_valid is False
            assert "unsupported" in error.lower()
        finally:
            os.unlink(temp_path)

    def test_validate_audio_file_valid(self) -> None:
        """Validation should pass for valid audio file."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"fake audio content")
            temp_path = f.name

        try:
            is_valid, error = validate_audio_file(temp_path)
            assert is_valid is True
            assert error is None
        finally:
            os.unlink(temp_path)


# =============================================================================
# Image Tools Tests
# =============================================================================


class TestImageValidation:
    """Tests for image file validation."""

    def test_is_image_file_jpg(self) -> None:
        """JPG should be recognized as image."""
        assert is_image_file("test.jpg") is True

    def test_is_image_file_jpeg(self) -> None:
        """JPEG should be recognized as image."""
        assert is_image_file("test.jpeg") is True

    def test_is_image_file_png(self) -> None:
        """PNG should be recognized as image."""
        assert is_image_file("test.png") is True

    def test_is_image_file_webp(self) -> None:
        """WebP should be recognized as image."""
        assert is_image_file("test.webp") is True

    def test_is_image_file_mp3(self) -> None:
        """MP3 should not be recognized as image."""
        assert is_image_file("test.mp3") is False

    def test_is_image_file_pdf(self) -> None:
        """PDF should not be recognized as image."""
        assert is_image_file("test.pdf") is False

    def test_validate_image_file_not_found(self) -> None:
        """Validation should fail for non-existent file."""
        is_valid, error = validate_image_file("/nonexistent/file.jpg")
        assert is_valid is False
        assert "not found" in error.lower()

    def test_validate_image_file_unsupported_format(self) -> None:
        """Validation should fail for unsupported format."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            is_valid, error = validate_image_file(temp_path)
            assert is_valid is False
            assert "unsupported" in error.lower()
        finally:
            os.unlink(temp_path)

    def test_get_image_mime_type_jpg(self) -> None:
        """JPG should return image/jpeg MIME type."""
        assert get_image_mime_type("test.jpg") == "image/jpeg"

    def test_get_image_mime_type_png(self) -> None:
        """PNG should return image/png MIME type."""
        assert get_image_mime_type("test.png") == "image/png"

    def test_get_image_mime_type_webp(self) -> None:
        """WebP should return image/webp MIME type."""
        assert get_image_mime_type("test.webp") == "image/webp"


# =============================================================================
# Document Tools Tests
# =============================================================================


class TestDocumentValidation:
    """Tests for document file validation."""

    def test_is_document_file_pdf(self) -> None:
        """PDF should be recognized as document."""
        assert is_document_file("test.pdf") is True

    def test_is_document_file_txt(self) -> None:
        """TXT should be recognized as document."""
        assert is_document_file("test.txt") is True

    def test_is_document_file_docx(self) -> None:
        """DOCX should be recognized as document."""
        assert is_document_file("test.docx") is True

    def test_is_document_file_mp3(self) -> None:
        """MP3 should not be recognized as document."""
        assert is_document_file("test.mp3") is False

    def test_is_document_file_png(self) -> None:
        """PNG should not be recognized as document."""
        assert is_document_file("test.png") is False

    def test_validate_document_file_not_found(self) -> None:
        """Validation should fail for non-existent file."""
        is_valid, error = validate_document_file("/nonexistent/file.pdf")
        assert is_valid is False
        assert "not found" in error.lower()

    def test_validate_document_file_unsupported_format(self) -> None:
        """Validation should fail for unsupported format."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            is_valid, error = validate_document_file(temp_path)
            assert is_valid is False
            assert "unsupported" in error.lower()
        finally:
            os.unlink(temp_path)


class TestCleanExtractedText:
    """Tests for text cleaning utility."""

    def test_clean_removes_excessive_whitespace(self) -> None:
        """Should remove excessive whitespace."""
        text = "Line 1\n\n\n\nLine 2"
        cleaned = clean_extracted_text(text)
        assert cleaned == "Line 1\n\nLine 2"

    def test_clean_strips_lines(self) -> None:
        """Should strip whitespace from lines."""
        text = "  Line 1  \n  Line 2  "
        cleaned = clean_extracted_text(text)
        assert cleaned == "Line 1\nLine 2"

    def test_clean_removes_internal_spaces(self) -> None:
        """Should normalize internal spaces."""
        text = "Line   with    many   spaces"
        cleaned = clean_extracted_text(text)
        assert cleaned == "Line with many spaces"

    def test_clean_respects_max_lines(self) -> None:
        """Should truncate to max_lines."""
        text = "\n".join([f"Line {i}" for i in range(100)])
        cleaned = clean_extracted_text(text, max_lines=10)
        lines = cleaned.split("\n")
        assert len(lines) <= 12  # 10 lines + truncation message

    def test_clean_empty_text(self) -> None:
        """Should handle empty text."""
        assert clean_extracted_text("") == ""
        assert clean_extracted_text(None) == ""  # type: ignore[arg-type]


class TestDocumentExtraction:
    """Tests for document text extraction."""

    def test_extract_txt_file(self) -> None:
        """Should extract text from TXT file."""
        from src.mcp_servers.multimodal.document_tools import process_document

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("This is a test document.\nWith multiple lines.")
            temp_path = f.name

        try:
            result = process_document(temp_path)
            assert result["success"] is True
            assert "test document" in result["text"]
            assert result["format"] == "txt"
        finally:
            os.unlink(temp_path)

    def test_extract_empty_file(self) -> None:
        """Should handle empty file gracefully."""
        from src.mcp_servers.multimodal.document_tools import process_document

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
            f.write("")
            temp_path = f.name

        try:
            result = process_document(temp_path)
            assert result["success"] is False
            assert "empty" in result["error"].lower()
        finally:
            os.unlink(temp_path)


# =============================================================================
# File Type Detection Tests
# =============================================================================


class TestFileTypeDetection:
    """Tests for cross-tool file type detection."""

    def test_audio_extensions_are_exclusive(self) -> None:
        """Audio extensions should not be detected as image or document."""
        audio_files = ["test.mp3", "test.wav", "test.flac", "test.ogg"]
        for f in audio_files:
            assert is_audio_file(f) is True
            assert is_image_file(f) is False
            assert is_document_file(f) is False

    def test_image_extensions_are_exclusive(self) -> None:
        """Image extensions should not be detected as audio or document."""
        image_files = ["test.jpg", "test.png", "test.webp", "test.gif"]
        for f in image_files:
            assert is_image_file(f) is True
            assert is_audio_file(f) is False
            assert is_document_file(f) is False

    def test_document_extensions_are_exclusive(self) -> None:
        """Document extensions should not be detected as audio or image."""
        doc_files = ["test.pdf", "test.txt", "test.docx"]
        for f in doc_files:
            assert is_document_file(f) is True
            assert is_audio_file(f) is False
            assert is_image_file(f) is False
