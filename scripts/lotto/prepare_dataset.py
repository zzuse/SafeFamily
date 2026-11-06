"""Turn a /lotto/export.zip into training data (step 3a, on the Mac).

Usage:
    python scripts/lotto/prepare_dataset.py ~/Downloads/lotto-labeled-20261106.zip

Writes two datasets from the same labels:

    lotto_data/yolo/                     # corner detector (train_detector.py)
        images/{train,val,test}/<photo>.jpg   upright photos
        labels/{train,val,test}/<photo>.txt   "0 cx cy w h" per price corner
        data.yaml
    lotto_data/crops/{train,val,test}/   # value reader (train_crnn.py)
    lotto_data/{train,val,test}.tsv      # "crops/...png<TAB>value"
    lotto_data/charset.txt

Both are rebuilt from scratch each time, so always run it on the newest export.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from collections import Counter
from pathlib import Path

from lotto_common import crop_box, default_data_dir, load_upright, read_manifest
from PIL import Image

SPLITS = ("train", "val", "test")


def write_yolo_image(  # noqa: PLR0913
    image: Image.Image, boxes: list[dict], stem: str, root: Path, *, split: str, max_side: int,
) -> None:
    """Save an upright photo and its YOLO label file (one class: price corner)."""
    images_dir = root / "images" / split
    labels_dir = root / "labels" / split
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    scale = min(1.0, max_side / max(image.size))
    if scale < 1.0:
        image = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    image.save(images_dir / f"{stem}.jpg", quality=92)
    # Box coordinates are fractions of the image, so resizing doesn't change them.
    lines = [
        f"0 {b['x'] + b['w'] / 2:.6f} {b['y'] + b['h'] / 2:.6f} {b['w']:.6f} {b['h']:.6f}" for b in boxes
    ]
    (labels_dir / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))


def write_data_yaml(root: Path, counts: Counter[str]) -> None:
    """Describe the YOLO dataset; fall back to train when val/test are empty."""
    val = "val" if counts["val"] else "train"
    test = "test" if counts["test"] else val
    (root / "data.yaml").write_text(
        f"path: {root.resolve()}\n"
        f"train: images/train\nval: images/{val}\ntest: images/{test}\n"
        "names:\n  0: price_corner\n",
    )


def main() -> None:
    """Build the detector and reader datasets from labeled photos."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("zip", type=Path, help="export zip downloaded from /lotto (scope=labeled)")
    parser.add_argument("--data", type=Path, default=default_data_dir(), help="output folder (default: lotto_data)")
    parser.add_argument("--pad", type=float, default=0.08, help="margin around each crop, as a fraction of its size")
    parser.add_argument("--max-side", type=int, default=2560, help="longest side of detector photos, in pixels")
    args = parser.parse_args()

    crops_dir = args.data / "crops"
    yolo_dir = args.data / "yolo"
    for folder in (crops_dir, yolo_dir):
        if folder.exists():
            shutil.rmtree(folder)
    rows: dict[str, list[str]] = {split: [] for split in SPLITS}
    photos: Counter[str] = Counter()
    values: Counter[str] = Counter()
    chars: Counter[str] = Counter()

    with zipfile.ZipFile(args.zip) as archive:
        entries = [e for e in read_manifest(archive) if e.labeled]
        for entry in entries:
            split = entry.split if entry.split in SPLITS else "train"
            boxes = [b for b in entry.boxes if b.get("label")]
            image = load_upright(archive.read(entry.file), entry.rotation)
            write_yolo_image(image, boxes, entry.id, yolo_dir, split=split, max_side=args.max_side)
            photos[split] += 1
            out_dir = crops_dir / split
            out_dir.mkdir(parents=True, exist_ok=True)
            for index, box in enumerate(boxes):
                path = out_dir / f"{entry.id}_{index}.png"
                crop_box(image, box, args.pad).save(path)
                rows[split].append(f"{path.relative_to(args.data)}\t{box['label']}")
                values[box["label"]] += 1
                chars.update(box["label"])

    args.data.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        (args.data / f"{split}.tsv").write_text("\n".join(rows[split]) + ("\n" if rows[split] else ""))
    (args.data / "charset.txt").write_text("".join(sorted(chars)))
    if entries:
        write_data_yaml(yolo_dir, photos)

    print(f"Photos: {len(entries)}")
    for split in SPLITS:
        print(f"  {split:5s}: {photos[split]:4d} photos, {len(rows[split]):5d} price corners")
    by_value = sorted(values.items(), key=lambda kv: (len(kv[0]), kv[0]))
    print("Corners per value: " + ", ".join(f"${v}: {n}" for v, n in by_value))
    print(f"Open {crops_dir} in Finder: every crop should show one upright price corner.")


if __name__ == "__main__":
    main()
