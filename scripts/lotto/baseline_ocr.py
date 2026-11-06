"""Score off-the-shelf OCR before training anything (on the Mac).

Two checks:

* ``--count`` (start here): run OCR on whole photos, count every "$5", "$10",
  ... it finds, and compare with your per-value counts. If that is already
  exact, you may not need to train at all.
* default: read each labeled price-corner crop and compare with its value.
  This tells you whether OCR could replace the value reader (train_crnn.py).

Engines:
    vision     Apple's Live Text engine (macOS only):  pip install ocrmac
    tesseract  brew install tesseract && pip install pytesseract

Usage:
    python scripts/lotto/baseline_ocr.py --count --split test
    python scripts/lotto/baseline_ocr.py --engine vision --split test
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from lotto_common import default_data_dir
from PIL import Image, ImageOps

MIN_HEIGHT = 64
GOOD_ENOUGH = 0.98
# A price on its own, optionally followed by the game number: "$5", "$10 16137".
# Prize text like "$100,000" or "$1,000,000" does not match.
PRICE_RE = re.compile(r"^\$\s?(\d{1,3})(?:\s+\d{4,6})?$")


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


def ocr_prices(image: Image.Image) -> Counter[str]:
    """Count price tokens Apple Vision finds on a whole photo."""
    from ocrmac import ocrmac  # noqa: PLC0415 - optional, macOS-only dependency

    results = ocrmac.OCR(image, recognition_level="accurate", language_preference=["en-US"]).recognize()
    found: Counter[str] = Counter()
    for text, _conf, _bbox in results:
        match = PRICE_RE.match(text.strip())
        if match:
            found[match.group(1)] += 1
    return found


def count_check(data: Path, split: str) -> None:
    """Compare OCR price counts with your labels on every photo of ``split``."""
    human: dict[str, Counter[str]] = {}
    for path, label in read_rows(data, split):
        human.setdefault(path.name.rsplit("_", 1)[0], Counter())[label] += 1
    if not human:
        msg = f"No labeled {split} photos yet: label more and re-run prepare_dataset.py."
        raise SystemExit(msg)
    exact = 0
    for photo_id, counts in sorted(human.items()):
        image = Image.open(data / "yolo" / "images" / split / f"{photo_id}.jpg")
        found = ocr_prices(image)
        exact += found == counts
        mark = "✓" if found == counts else ""
        print(f"  {photo_id[:8]}  you {dict(sorted(counts.items()))}  ocr {dict(sorted(found.items()))} {mark}")
    print(f"Apple Vision counted every value exactly right on {exact}/{len(human)} {split} photos.")
    if exact == len(human):
        print("Good enough to use as-is; training is optional.")
    else:
        print("Train the corner detector and value reader (train_detector.py, train_crnn.py).")


def main() -> None:
    """Print exact-match accuracy and the misses."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", choices=("vision", "tesseract"), default="vision")
    parser.add_argument("--split", default="test", help="train, val or test (default test)")
    parser.add_argument("--data", type=Path, default=default_data_dir())
    parser.add_argument("--count", action="store_true", help="count prices on whole photos (Apple Vision)")
    args = parser.parse_args()

    if args.count:
        count_check(args.data, args.split)
        return

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
        print("Train the value reader (train_crnn.py).")


if __name__ == "__main__":
    main()
