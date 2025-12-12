"""
Image Analysis Tools - VLM-based image analysis.
"""

import base64
import logging
import os
from pathlib import Path
from typing import Any, Literal

from src.core.telemetry import get_tracer, traced_operation

logger = logging.getLogger(__name__)
tracer = get_tracer("copforge.mcp.multimodal.image")

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

# Analysis type prompts
ANALYSIS_PROMPTS = {
    "general": """Analyze this tactical imagery and provide a detailed report including:
1. **Assets Detected**: Military vehicles, aircraft, vessels, equipment (type, quantity, location)
2. **Personnel**: Military or civilian personnel (count, activity)
3. **Infrastructure**: Buildings, roads, bridges, installations (type, condition)
4. **Terrain**: Environment type and tactical implications
5. **Threat Assessment**: Classification (friendly/hostile/unknown), threat level
6. **Additional Observations**: Any other tactically relevant information""",
    "asset_detection": """Perform detailed military asset detection on this image.
For EACH asset detected, provide:
- **Asset Type**: (aircraft, tank, APC, artillery, truck, vessel, etc.)
- **Classification**: Friendly/Hostile/Unknown
- **Quantity**: How many visible
- **Location**: Position in image
- **Heading**: Direction if visible
- **Status**: Active/stationary/abandoned/damaged
- **Confidence**: High/Medium/Low

If NO military assets detected, explicitly state that.""",
    "terrain": """Analyze the terrain and geographic features:
1. **Terrain Type**: (urban, rural, desert, forest, mountain, coastal, etc.)
2. **Elevation**: Flat, hilly, mountainous
3. **Vegetation**: Density and type
4. **Water Features**: Rivers, lakes, coastline
5. **Roads/Paths**: Quality and type
6. **Cover and Concealment**: Available natural/artificial cover
7. **Tactical Advantages/Disadvantages**
8. **Mobility Assessment**: Vehicle and personnel mobility""",
    "damage": """Perform damage assessment:
1. **Structures Affected**: Damage level (destroyed/heavily/moderately/lightly damaged)
2. **Equipment/Vehicles**: Damaged or destroyed assets
3. **Overall Assessment**: Total structures, percentage damaged
4. **Operational Impact**: Effect on tactical operations
5. **Potential Causes**: Combat, natural disaster, etc.""",
}

AnalysisType = Literal["general", "asset_detection", "terrain", "damage", "custom"]


def is_image_file(file_path: str) -> bool:
    """Check if file is a supported image format."""
    return Path(file_path).suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


def validate_image_file(image_path: str) -> tuple[bool, str | None]:
    """Validate image file exists and is supported."""
    if not os.path.exists(image_path):
        return False, f"Image file not found: {image_path}"
    extension = Path(image_path).suffix.lower()
    if extension not in SUPPORTED_IMAGE_EXTENSIONS:
        return False, f"Unsupported image format: {extension}"
    file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
    if file_size_mb > 20:
        return False, f"Image too large: {file_size_mb:.1f}MB (max 20MB)"
    return True, None


def encode_image_to_base64(image_path: str) -> str | None:
    """Encode image file to base64 string."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Error encoding image: {e}")
        return None


def get_image_mime_type(image_path: str) -> str:
    """Get MIME type from image file extension."""
    extension = Path(image_path).suffix.lower()
    return MIME_TYPES.get(extension, "image/jpeg")


def analyze_image_with_vlm(
    image_path: str,
    prompt: str,
    model: str = "gpt-4o",
    max_tokens: int = 1000,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """
    Analyze image using a Vision Language Model.

    Args:
        image_path: Path to image file
        prompt: Analysis prompt
        model: Model identifier (gpt-4o, claude-3-5-sonnet, etc.)
        max_tokens: Maximum tokens in response
        temperature: Generation temperature

    Returns:
        Dict with analysis result
    """
    with traced_operation(tracer, "analyze_image_with_vlm", {"model": model}) as span:
        try:
            is_valid, error = validate_image_file(image_path)
            if not is_valid:
                return {"success": False, "analysis": "", "model_used": model, "error": error}

            base64_image = encode_image_to_base64(image_path)
            if not base64_image:
                return {
                    "success": False,
                    "analysis": "",
                    "model_used": model,
                    "error": "Failed to encode image",
                }

            mime_type = get_image_mime_type(image_path)

            # Use LangChain for provider abstraction
            from langchain_core.messages import HumanMessage
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(model=model, max_tokens=max_tokens, temperature=temperature)
            message = HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}",
                            "detail": "high",
                        },
                    },
                ]
            )

            logger.info(f"Analyzing image with {model}...")
            response = llm.invoke([message])

            span.set_attribute("image.model", model)
            return {
                "success": True,
                "analysis": response.content,
                "model_used": model,
                "error": None,
            }

        except Exception as e:
            logger.exception("Vision analysis failed")
            return {
                "success": False,
                "analysis": "",
                "model_used": model,
                "error": f"Vision analysis failed: {e!s}",
            }


def analyze_image(
    image_path: str,
    analysis_type: AnalysisType = "general",
    custom_prompt: str | None = None,
    model: str = "gpt-4o",
) -> dict[str, Any]:
    """
    High-level tactical image analysis function.

    Args:
        image_path: Path to image file
        analysis_type: Type of analysis (general, asset_detection, terrain, damage, custom)
        custom_prompt: Custom prompt (required if analysis_type="custom")
        model: VLM model to use

    Returns:
        Dict with analysis result
    """
    with traced_operation(tracer, "analyze_image", {"analysis_type": analysis_type}) as span:
        file_name = Path(image_path).name

        # Select prompt
        if analysis_type == "custom":
            if not custom_prompt:
                return {
                    "success": False,
                    "file_name": file_name,
                    "analysis_type": analysis_type,
                    "analysis": "",
                    "model_used": model,
                    "error": "custom_prompt required when analysis_type='custom'",
                }
            prompt = custom_prompt
        elif analysis_type in ANALYSIS_PROMPTS:
            prompt = ANALYSIS_PROMPTS[analysis_type]
        else:
            return {
                "success": False,
                "file_name": file_name,
                "analysis_type": analysis_type,
                "analysis": "",
                "model_used": model,
                "error": f"Invalid analysis_type: {analysis_type}",
            }

        # Perform analysis
        result = analyze_image_with_vlm(
            image_path=image_path,
            prompt=prompt,
            model=model,
            max_tokens=1500 if analysis_type == "general" else 1000,
        )

        span.set_attribute("image.success", result["success"])

        if not result["success"]:
            return {
                "success": False,
                "file_name": file_name,
                "analysis_type": analysis_type,
                "analysis": "",
                "model_used": model,
                "error": result["error"],
            }

        return {
            "success": True,
            "file_name": file_name,
            "analysis_type": analysis_type,
            "analysis": result["analysis"],
            "model_used": result["model_used"],
            "error": None,
        }
