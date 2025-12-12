# MCP Server: Multimodal

Tools for processing audio, images, and documents from tactical sensors.

## Architecture

```bash
                    MCP SERVER: MULTIMODAL
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  TOOLS:                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ transcribe_audio│  │  analyze_image  │  │ process_doc │  │
│  │                 │  │                 │  │             │  │
│  │ • Whisper STT   │  │ • GPT-4V/Claude │  │ • PyPDF2    │  │
│  │ • Pyannote      │  │ • Asset detect  │  │ • python-   │  │
│  │   diarization   │  │ • Terrain       │  │   docx      │  │
│  │ • Multi-speaker │  │ • Damage assess │  │ • Multi-enc │  │
│  └─────────────────┘  └─────────────────┘  └─────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         ↓                      ↓                    ↓
    Transcription           Analysis             Extracted
       Text              Description               Text
         ↓                      ↓                    ↓
┌─────────────────────────────────────────────────────────────┐
│                      INGEST AGENT                           │
│                                                             │
│  LLM extracts entities from multimodal output               │
│  with tactical context from COP                             │
└─────────────────────────────────────────────────────────────┘
```

## Tools

### 1. `transcribe_audio`

Transcribe audio files using Whisper with optional speaker diarization.

**Supported formats**: mp3, wav, m4a, flac, ogg, aac, wma

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| audio_path | string | required | Path to audio file |
| enable_diarization | boolean | true | Enable speaker identification |
| num_speakers | integer | null | Expected speakers (null=auto) |
| language | string | null | ISO code (null=auto-detect) |

**Requirements**:

- `pip install openai-whisper`
- `pip install pyannote.audio` (for diarization)
- `HF_TOKEN` environment variable (for pyannote)
- `ffmpeg` installed

### 2. `analyze_image`

Analyze images using Vision Language Models (VLM).

**Supported formats**: jpg, jpeg, png, gif, bmp, webp, tiff

**Analysis types**:

| Type | Description |
|------|-------------|
| general | Full tactical assessment |
| asset_detection | Military vehicles, aircraft, equipment |
| terrain | Geographic and terrain analysis |
| damage | Damage assessment |
| custom | Use custom_prompt |

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| image_path | string | required | Path to image file |
| analysis_type | string | "general" | Type of analysis |
| custom_prompt | string | null | Custom prompt for "custom" type |
| model | string | "gpt-4o" | VLM model to use |

**Requirements**:

- `pip install langchain-openai`
- `OPENAI_API_KEY` environment variable

### 3. `process_document`

Extract text from documents.

**Supported formats**: pdf, txt, docx

**Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| document_path | string | required | Path to document file |
| max_lines | integer | 1000 | Maximum lines to extract |

**Requirements**:
- `pip install PyPDF2` (for PDF)
- `pip install python-docx` (for DOCX)

## Output Format

All tools return structured reports for LLM consumption:

```bash
AUDIO TRANSCRIPTION REPORT
==========================
File: radio_intercept.mp3
Duration: 45.3 seconds
Language: en
Speakers: 2 detected
Status: SUCCESS

TRANSCRIPTION:
--------------
SPEAKER_00 [0.0s - 12.5s]: Alpha team, this is command...
SPEAKER_01 [13.2s - 28.7s]: Command, alpha team. We have visual...
==========================
```

## Running

```bash
# Standalone
uv run python -m src.mcp_servers.multimodal.server

# With MCP Inspector
npx @anthropic/mcp-inspector uv run python -m src.mcp_servers.multimodal.server
```

## Claude Desktop Configuration

```json
{
  "mcpServers": {
    "multimodal": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp_servers.multimodal.server"],
      "cwd": "/path/to/copforge",
      "env": {
        "OPENAI_API_KEY": "your-key",
        "HF_TOKEN": "your-token"
      }
    }
  }
}
```

## Dependencies

```toml
[project.optional-dependencies]
multimodal = [
    "openai-whisper",
    "pyannote.audio",
    "langchain-openai",
    "PyPDF2",
    "python-docx",
    "Pillow",
]
```
