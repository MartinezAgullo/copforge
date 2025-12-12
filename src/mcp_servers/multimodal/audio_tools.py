"""
Audio Processing Tools - Transcription using Whisper and Pyannote.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from src.core.telemetry import get_tracer, traced_operation

logger = logging.getLogger(__name__)
tracer = get_tracer("copforge.mcp.multimodal.audio")

SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma"}

# Lazy-loaded models
_whisper_model: Any = None
_diarization_pipeline: Any = None


def _load_whisper_model(model_size: str = "medium") -> Any:
    """Lazy load Whisper model."""
    global _whisper_model
    if _whisper_model is None:
        try:
            import whisper

            logger.info(f"Loading Whisper {model_size} model...")
            _whisper_model = whisper.load_model(model_size)
            logger.info(f"Whisper {model_size} model loaded")
        except ImportError as e:
            raise ImportError(
                "Whisper not installed. Install with: pip install openai-whisper"
            ) from e
    return _whisper_model


def _load_diarization_pipeline() -> Any:
    """Lazy load pyannote speaker diarization pipeline."""
    global _diarization_pipeline
    if _diarization_pipeline is None:
        try:
            from pyannote.audio import Pipeline

            hf_token = os.getenv("HF_TOKEN")
            if not hf_token:
                raise ValueError(
                    "HF_TOKEN not found. Get token from: https://huggingface.co/settings/tokens"
                )
            logger.info("Loading pyannote speaker-diarization-3.1 model...")
            _diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", use_auth_token=hf_token
            )
            logger.info("Diarization pipeline loaded")
        except ImportError as e:
            raise ImportError(
                "Pyannote not installed. Install with: pip install pyannote.audio"
            ) from e
    return _diarization_pipeline


def is_audio_file(file_path: str) -> bool:
    """Check if file is a supported audio format."""
    return Path(file_path).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


def validate_audio_file(audio_path: str) -> tuple[bool, str | None]:
    """Validate audio file exists and is supported."""
    if not os.path.exists(audio_path):
        return False, f"Audio file not found: {audio_path}"
    if not is_audio_file(audio_path):
        return False, f"Unsupported audio format: {Path(audio_path).suffix}"
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if file_size_mb > 100:
        return False, f"Audio file too large: {file_size_mb:.1f}MB (max 100MB)"
    return True, None


def transcribe_audio_simple(
    audio_path: str, language: str | None = None, model_size: str = "medium"
) -> dict[str, Any]:
    """Simple audio transcription without speaker diarization."""
    with traced_operation(tracer, "transcribe_audio_simple", {"audio_path": audio_path}) as span:
        try:
            is_valid, error = validate_audio_file(audio_path)
            if not is_valid:
                return {
                    "success": False,
                    "transcription": "",
                    "language": None,
                    "duration": 0.0,
                    "error": error,
                }

            model = _load_whisper_model(model_size)
            logger.info(f"Transcribing: {Path(audio_path).name}")
            result = model.transcribe(audio_path, language=language)

            span.set_attribute("audio.language", result.get("language", "unknown"))
            return {
                "success": True,
                "transcription": result["text"].strip(),
                "language": result.get("language", "unknown"),
                "duration": result.get("duration", 0.0),
                "segments": result.get("segments", []),
                "error": None,
            }
        except Exception as e:
            logger.exception("Transcription failed")
            return {
                "success": False,
                "transcription": "",
                "language": None,
                "duration": 0.0,
                "error": f"Transcription failed: {e!s}",
            }


def transcribe_audio_with_speakers(
    audio_path: str,
    num_speakers: int | None = None,
    min_speakers: int = 1,
    max_speakers: int = 4,
    language: str | None = None,
    model_size: str = "medium",
) -> dict[str, Any]:
    """Audio transcription with speaker diarization."""
    with traced_operation(
        tracer, "transcribe_audio_with_speakers", {"audio_path": audio_path}
    ) as span:
        try:
            is_valid, error = validate_audio_file(audio_path)
            if not is_valid:
                return {
                    "success": False,
                    "transcription": "",
                    "speakers": [],
                    "num_speakers_detected": 0,
                    "language": None,
                    "duration": 0.0,
                    "error": error,
                }

            diar_pipeline = _load_diarization_pipeline()
            whisper_model = _load_whisper_model(model_size)

            logger.info(f"Performing speaker diarization on: {Path(audio_path).name}")
            if num_speakers is not None:
                diarization = diar_pipeline(audio_path, num_speakers=num_speakers)
            else:
                diarization = diar_pipeline(
                    audio_path, min_speakers=min_speakers, max_speakers=max_speakers
                )

            speakers_detected = {
                speaker for _, _, speaker in diarization.itertracks(yield_label=True)
            }
            num_speakers_detected = len(speakers_detected)
            logger.info(f"Detected {num_speakers_detected} speaker(s)")

            speaker_segments: list[dict[str, Any]] = []
            detected_language = "unknown"

            for turn, _, speaker in diarization.itertracks(yield_label=True):
                start_time, end_time = turn.start, turn.end
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    tmp_path = tmp_file.name

                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        audio_path,
                        "-ss",
                        str(start_time),
                        "-to",
                        str(end_time),
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        tmp_path,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )

                result = whisper_model.transcribe(tmp_path, language=language)
                text = result["text"].strip()
                detected_language = result.get("language", "unknown")
                os.unlink(tmp_path)

                if text:
                    speaker_segments.append(
                        {
                            "speaker": speaker,
                            "start": round(start_time, 2),
                            "end": round(end_time, 2),
                            "duration": round(end_time - start_time, 2),
                            "text": text,
                        }
                    )

            formatted_lines = [
                f"{seg['speaker']} [{seg['start']:.1f}s - {seg['end']:.1f}s]: {seg['text']}"
                for seg in speaker_segments
            ]
            full_transcription = "\n".join(formatted_lines)
            total_duration = speaker_segments[-1]["end"] if speaker_segments else 0.0

            span.set_attribute("audio.speakers", num_speakers_detected)
            return {
                "success": True,
                "transcription": full_transcription,
                "speakers": speaker_segments,
                "num_speakers_detected": num_speakers_detected,
                "language": detected_language,
                "duration": total_duration,
                "error": None,
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "transcription": "",
                "speakers": [],
                "num_speakers_detected": 0,
                "language": None,
                "duration": 0.0,
                "error": f"FFmpeg error: {e!s}",
            }
        except Exception as e:
            logger.exception("Diarization/transcription failed")
            return {
                "success": False,
                "transcription": "",
                "speakers": [],
                "num_speakers_detected": 0,
                "language": None,
                "duration": 0.0,
                "error": f"Failed: {e!s}",
            }


def transcribe_audio(
    audio_path: str,
    enable_diarization: bool = True,
    num_speakers: int | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """
    High-level audio transcription function.

    Args:
        audio_path: Path to audio file
        enable_diarization: Whether to use speaker diarization
        num_speakers: Expected number of speakers (None = auto-detect)
        language: ISO language code (None = auto-detect)

    Returns:
        Dict with transcription result
    """
    with traced_operation(
        tracer, "transcribe_audio", {"enable_diarization": enable_diarization}
    ) as span:
        if enable_diarization:
            result = transcribe_audio_with_speakers(
                audio_path=audio_path, num_speakers=num_speakers, language=language
            )
        else:
            result = transcribe_audio_simple(audio_path=audio_path, language=language)

        span.set_attribute("audio.success", result["success"])
        file_name = Path(audio_path).name

        if not result["success"]:
            return {
                "success": False,
                "file_name": file_name,
                "transcription": "",
                "language": None,
                "duration": 0.0,
                "num_speakers": 0,
                "error": result["error"],
            }

        return {
            "success": True,
            "file_name": file_name,
            "transcription": result["transcription"],
            "language": result["language"],
            "duration": result["duration"],
            "num_speakers": result.get("num_speakers_detected", 1),
            "speakers": result.get("speakers", []),
            "error": None,
        }
