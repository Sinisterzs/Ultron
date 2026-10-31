"""
plugins/_smart_vision_capture.py — On-demand screen, monitor, and region capture.

Uses `mss` and Pillow in memory without creating temporary files on disk.
Enforces pixel and byte limits, calculates cryptographic SHA-256 digests,
and validates target geometry and multi-monitor bounds.
"""
from __future__ import annotations

import hashlib
import io
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Union

try:
    import mss
    import mss.tools
    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False

try:
    import PIL.Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


@dataclass
class CaptureArtifact:
    """In-memory representation of an authorized screen capture."""
    id: str
    data: bytes
    mime_type: str
    width: int
    height: int
    timestamp: float
    source: str
    target: str
    sha256: str

    def size_bytes(self) -> int:
        return len(self.data)


# Dimension limits per profile
_PROFILES = {
    "balanced": (1280, 720, 82),      # (max_w, max_h, jpeg_quality)
    "high_detail": (1920, 1080, 88),
    "compact": (854, 480, 75),
}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB maximum bound


class ScreenCapturer:
    """Handles thread-safe on-demand screen and region capture."""

    def __init__(self):
        if not _MSS_AVAILABLE:
            raise RuntimeError("mss is not installed. Screen capture is unavailable.")
        if not _PIL_AVAILABLE:
            raise RuntimeError("PIL (Pillow) is not installed. Image processing is unavailable.")

    @staticmethod
    def parse_region(region_input: Union[str, tuple, list, dict, None]) -> Optional[dict[str, int]]:
        """Parse region input into {'top': y, 'left': x, 'width': w, 'height': h}."""
        if not region_input:
            return None
        if isinstance(region_input, dict):
            top = int(region_input.get("top", region_input.get("y", 0)))
            left = int(region_input.get("left", region_input.get("x", 0)))
            width = int(region_input.get("width", region_input.get("w", 0)))
            height = int(region_input.get("height", region_input.get("h", 0)))
        elif isinstance(region_input, (tuple, list)):
            if len(region_input) != 4:
                raise ValueError("Region list/tuple must have 4 elements: (x, y, w, h)")
            left, top, width, height = (int(v) for v in region_input)
        elif isinstance(region_input, str):
            parts = [p.strip() for p in region_input.split(",")]
            if len(parts) != 4:
                raise ValueError(f"Region string must be 'x,y,w,h', got '{region_input}'")
            left, top, width, height = (int(p) for p in parts)
        else:
            raise ValueError(f"Unsupported region format: {type(region_input)}")

        if width <= 0 or height <= 0:
            raise ValueError(f"Region width and height must be positive, got {width}x{height}")
        return {"left": left, "top": top, "width": width, "height": height}

    def capture(self, target: str = "screen",
                region: Union[str, tuple, list, dict, None] = None,
                profile: str = "balanced",
                max_bytes: int = MAX_IMAGE_BYTES) -> CaptureArtifact:
        """Perform on-demand capture, compress in-memory, and return a CaptureArtifact."""
        parsed_region = self.parse_region(region)
        max_w, max_h, quality = _PROFILES.get(profile, _PROFILES["balanced"])

        with mss.mss() as sct:
            monitors = sct.monitors  # [0] = all combined, [1..n] = individual screens
            if parsed_region is not None:
                # Region capture
                grab_box = parsed_region
                effective_target = (f"region({grab_box['left']},{grab_box['top']},"
                                    f"{grab_box['width']},{grab_box['height']})")
            elif target.startswith("monitor_"):
                try:
                    idx = int(target.replace("monitor_", "").strip())
                    if idx < 1 or idx >= len(monitors):
                        raise IndexError(f"Monitor {idx} out of range (detected 1..{len(monitors)-1})")
                    grab_box = monitors[idx]
                    effective_target = f"monitor_{idx}"
                except ValueError:
                    raise ValueError(f"Invalid monitor target '{target}'")
            elif target == "all":
                grab_box = monitors[0]
                effective_target = "all_monitors"
            else:
                # Default primary monitor or virtual screen
                grab_box = monitors[1] if len(monitors) > 1 else monitors[0]
                effective_target = "screen"

            shot = sct.grab(grab_box)
            # Create PIL image directly from raw RGB
            img = PIL.Image.frombytes("RGB", shot.size, shot.rgb)

        # Scale down if exceeds profile bounds
        if img.width > max_w or img.height > max_h:
            img.thumbnail((max_w, max_h), PIL.Image.BILINEAR)

        # In-memory JPEG compression
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=False)
        jpeg_bytes = buf.getvalue()

        if len(jpeg_bytes) > max_bytes:
            # If still over byte limit, recompress with lower quality
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60, optimize=True)
            jpeg_bytes = buf.getvalue()
            if len(jpeg_bytes) > max_bytes:
                raise RuntimeError(
                    f"Captured image exceeds maximum allowed size ({len(jpeg_bytes)} > {max_bytes} bytes)"
                )

        sha = hashlib.sha256(jpeg_bytes).hexdigest()
        artifact_id = str(uuid.uuid4())

        return CaptureArtifact(
            id=artifact_id,
            data=jpeg_bytes,
            mime_type="image/jpeg",
            width=img.width,
            height=img.height,
            timestamp=time.monotonic(),
            source="screen",
            target=effective_target,
            sha256=sha,
        )
