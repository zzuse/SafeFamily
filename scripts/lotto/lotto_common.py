"""Shared helpers for the lotto training scripts (run on the Mac, not the server).

The website stores untouched originals plus a manifest. These helpers turn
one manifest entry into upright, cropped ticket-number images exactly the way
the labeling page displays them:

1. apply the EXIF orientation (browsers do this automatically),
2. rotate clockwise by ``rotation`` degrees,
3. crop each box (0-1 fractions of the rotated image) with a small margin.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageOps

if TYPE_CHECKING:
    import zipfile


@dataclass
class Entry:
    """One photo from manifest.jsonl."""

    id: str
    file: str
    rotation: int
    split: str
    labeled: bool
    boxes: list[dict]


def read_manifest(archive: zipfile.ZipFile) -> list[Entry]:
    """Parse manifest.jsonl inside an export zip."""
    entries = []
    for line in archive.read("manifest.jsonl").decode("utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        if raw.get("skipped"):
            continue
        entries.append(
            Entry(
                id=raw["id"],
                file=raw["file"],
                rotation=int(raw.get("rotation") or 0),
                split=raw.get("split") or "train",
                labeled=bool(raw.get("labeled")),
                boxes=list(raw.get("boxes") or []),
            ),
        )
    return entries


def load_upright(data: bytes, rotation: int) -> Image.Image:
    """Open image bytes and rotate them upright like the labeling page does."""
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image).convert("RGB")
    if rotation % 360:
        # PIL rotates counter-clockwise; the page rotates clockwise.
        image = image.rotate(-rotation, expand=True)
    return image


def crop_box(image: Image.Image, box: dict, pad: float = 0.08) -> Image.Image:
    """Crop one box, adding ``pad`` x box size of margin on every side."""
    width, height = image.size
    bw, bh = box["w"] * width, box["h"] * height
    left = max(0, int(box["x"] * width - pad * bw))
    top = max(0, int(box["y"] * height - pad * bh))
    right = min(width, int((box["x"] + box["w"]) * width + pad * bw))
    bottom = min(height, int((box["y"] + box["h"]) * height + pad * bh))
    return image.crop((left, top, max(right, left + 1), max(bottom, top + 1)))


def crops_for_entry(archive: zipfile.ZipFile, entry: Entry, pad: float = 0.08) -> list[Image.Image]:
    """Return one crop per box of a manifest entry, in box order."""
    if not entry.boxes:
        return []
    image = load_upright(archive.read(entry.file), entry.rotation)
    return [crop_box(image, box, pad) for box in entry.boxes]


def default_data_dir() -> Path:
    """Where prepared crops and models live (override with --data)."""
    return Path("lotto_data")
