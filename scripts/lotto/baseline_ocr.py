"""Score off-the-shelf OCR on your labeled crops (step 3b, on the Mac).

Run this BEFORE training: if an existing engine already reads your ticket
numbers reliably, you can skip training and just use it.

Engines:
    vision     Apple's Live Text engine (macOS only):  pip install ocrmac
    tesseract  brew install tesseract && pip install pytesseract

Usage:
    python scripts/lotto/baseline_ocr.py --engine vision --split test
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from lotto_common import default_data_dir
from PIL import Image, ImageOps

MIN_HEIGHT = 64
GOOD_ENOUGH = 0.98


def read_rows(data: Path, split: str) -> list[tuple[Path, str]]:
    """Read ``split``.tsv written by prepare_dataset.py."""
    rows = []
    for line in (data / f"{split}.tsv").read_text().splitlines():
        if line.strip():
            path, label = line.split("\t")
            rows.append((data / path, label))
    return rows


def make_engine(name: str, charset: str):
    """Return a function image -> text for the chosen engine."""
    if name == "vision":
        from ocrmac import ocrmac  # noqa: PLC0415 - optional, macOS-only dependency

        def run(image: Image.Image) -> str:
            results = ocrmac.OCR(image, recognition_level="accurate", language_preference=["en-US"]).recognize()
            return "".join(text for text, _conf, _bbox in results)

        return run

    import pytesseract  # noqa: PLC0415 - optional dependency

    config = f"--psm 7 -c tessedit_char_whitelist={charset}"

    def run(image: Image.Image) -> str:
        return pytesseract.image_to_string(image, config=config)

    return run


def main() -> None:
    """Print exact-match accuracy and the misses."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=("vision", "tesseract"), default="vision")
    parser.add_argument("--split", default="test", help="train, val or test (default test)")
    parser.add_argument("--data", type=Path, default=default_data_dir())
    args = parser.parse_args()

    charset = (args.data / "charset.txt").read_text().strip() or "0123456789"
    allowed = re.compile(f"[^{re.escape(charset)}]")
    run = make_engine(args.engine, charset)
    rows = read_rows(args.data, args.split)
    if not rows:
        msg = f"No rows in {args.split}.tsv yet: label more photos and re-run prepare_dataset.py."
        raise SystemExit(msg)

    correct = 0
    for path, label in rows:
        image = Image.open(path).convert("L")
        # Upscale small crops: both engines like characters 30+ px tall.
        if image.height < MIN_HEIGHT:
            image = image.resize(
                (round(image.width * MIN_HEIGHT / image.height), MIN_HEIGHT),
                Image.Resampling.BICUBIC,
            )
        image = ImageOps.autocontrast(image)
        guess = allowed.sub("", run(image).upper())
        if guess == label:
            correct += 1
        else:
            print(f"  miss: {path.name}  label={label!r}  ocr={guess!r}")
    accuracy = correct / len(rows)
    print(f"{args.engine}: {correct}/{len(rows)} correct = {accuracy:.1%} on {args.split}")
    if accuracy >= GOOD_ENOUGH:
        print("Good enough to use as-is; training is optional.")
    else:
        print("Train the CRNN (train_crnn.py) once you have ~300 labeled numbers.")


if __name__ == "__main__":
    main()
