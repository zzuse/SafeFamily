"""Count tickets per value with the trained models (step 4, on the Mac).

Usage:
    python scripts/lotto/predict.py ~/Downloads/lotto-all-20261106.zip

For every photo: the detector finds the price corners, the reader reads each
corner's value, and the counts are tallied per value. Writes predictions.json;
upload it on the /lotto page ("Upload predictions.json"):

* unlabeled photos arrive pre-boxed with values filled in, so labeling turns
  into "fix the mistakes";
* labeled photos show "Model: N" next to your count, which is the honest
  accuracy check on photos the model never trained on.

Without --reader (or if lotto_data/models/lotto_crnn.pt is missing) only the
corners are found and their values are left blank.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter
from pathlib import Path

import torch
from lotto_common import crop_box, load_upright, read_manifest
from ultralytics import YOLO


def load_reader(path: Path, device: torch.device):
    """Load the value reader if it has been trained."""
    if not path.exists():
        print(f"No reader at {path}: values will be left blank.")
        return None
    from lotto_model import load_checkpoint  # noqa: PLC0415 - torch-heavy, optional

    return load_checkpoint(str(path), device)


def read_values(reader, crops: list, device: torch.device) -> list[tuple[str, float]]:  # noqa: ANN001
    """Read each crop's value with the CRNN; blanks when there is no reader."""
    if reader is None or not crops:
        return [("", 0.0)] * len(crops)
    from lotto_model import greedy_decode, to_tensor  # noqa: PLC0415

    model, charset = reader
    with torch.no_grad():
        batch = torch.stack([to_tensor(crop) for crop in crops]).to(device)
        return greedy_decode(model(batch), charset)


def by_value(item: tuple[str, int]) -> tuple[int, str]:
    """Sort tally items numerically: $5 before $10."""
    value = item[0]
    return (int(value), value) if value.isdigit() else (10**9, value)


def main() -> None:
    """Detect, read and tally every photo in the export."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("zip", type=Path, help="export zip from /lotto ('All photos' to include unlabeled ones)")
    parser.add_argument("--detector", type=Path, default=Path("lotto_data/models/corner_detector.pt"))
    parser.add_argument("--reader", type=Path, default=Path("lotto_data/models/lotto_crnn.pt"))
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--conf", type=float, default=0.35, help="minimum detector confidence to count a corner")
    parser.add_argument("--out", type=Path, default=Path("predictions.json"))
    args = parser.parse_args()

    from lotto_model import pick_device  # noqa: PLC0415

    device = pick_device()
    detector = YOLO(str(args.detector))
    reader = load_reader(args.reader, device)
    predictions: dict[str, dict] = {}
    checked = exact = 0

    with zipfile.ZipFile(args.zip) as archive:
        for entry in read_manifest(archive):
            image = load_upright(archive.read(entry.file), entry.rotation)
            found = detector.predict(image, imgsz=args.imgsz, conf=args.conf, device=str(device), verbose=False)[0]
            width, height = image.size
            boxes = []
            for (x1, y1, x2, y2), det_conf in zip(found.boxes.xyxy.tolist(), found.boxes.conf.tolist(), strict=True):
                boxes.append(
                    {"x": x1 / width, "y": y1 / height, "w": (x2 - x1) / width, "h": (y2 - y1) / height, "conf": det_conf},
                )
            boxes.sort(key=lambda b: (round(b["y"], 2), b["x"]))
            crops = [crop_box(image, box) for box in boxes]
            for box, (text, read_conf) in zip(boxes, read_values(reader, crops, device), strict=True):
                box["text"] = text
                # Both models must be sure for the box to count as sure.
                box["conf"] = round(box["conf"] * (read_conf if reader else 1.0), 4)
            predictions[entry.id] = {"boxes": boxes}

            model_tally = Counter(b["text"] or "?" for b in boxes)
            line = f"{entry.id[:8]}  model {len(boxes):3d}: " + ", ".join(
                f"${v}×{n}" for v, n in sorted(model_tally.items(), key=by_value)  # noqa: RUF001
            )
            if entry.labeled:
                human = Counter(b["label"] for b in entry.boxes if b.get("label"))
                checked += 1
                exact += human == model_tally
                line += f"   you {sum(human.values()):3d}: " + ", ".join(
                    f"${v}×{n}" for v, n in sorted(human.items(), key=by_value)  # noqa: RUF001
                )
                line += "  ✓" if human == model_tally else ""
            print(line)

    args.out.write_text(json.dumps(predictions, indent=1))
    print(f"Wrote predictions for {len(predictions)} photos to {args.out}")
    if checked:
        print(f"Labeled photos with every value counted exactly right: {exact}/{checked}")


if __name__ == "__main__":
    main()
