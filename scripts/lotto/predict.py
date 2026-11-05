"""Pre-label photos with the trained model (step 4, on the Mac).

Usage:
    python scripts/lotto/predict.py ~/Downloads/lotto-all-20261105.zip

Writes predictions.json; upload it on the /lotto page ("Upload
predictions.json"). Every box then shows the model's guess, and low-confidence
guesses are outlined in red, so labeling turns into "check and fix".

Photos that are already labeled are scored too, which tells you how the model
does on data it has never seen.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import torch
from lotto_common import crops_for_entry, read_manifest
from lotto_model import greedy_decode, load_checkpoint, pick_device, to_tensor


def main() -> None:
    """Predict every box in the export and write predictions.json."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("zip", type=Path, help="export zip from /lotto (use 'All photos' to include unlabeled ones)")
    parser.add_argument("--model", type=Path, default=Path("lotto_data/models/lotto_crnn.pt"))
    parser.add_argument("--out", type=Path, default=Path("predictions.json"))
    args = parser.parse_args()

    device = pick_device()
    model, charset = load_checkpoint(str(args.model), device)
    predictions: dict[str, list[dict]] = {}
    checked = correct = 0

    with zipfile.ZipFile(args.zip) as archive, torch.no_grad():
        for entry in read_manifest(archive):
            crops = crops_for_entry(archive, entry)
            if not crops:
                continue
            batch = torch.stack([to_tensor(crop) for crop in crops]).to(device)
            results = greedy_decode(model(batch), charset)
            predictions[entry.id] = [{"text": text, "conf": round(conf, 4)} for text, conf in results]
            for box, (text, _conf) in zip(entry.boxes, results, strict=True):
                if box.get("label"):
                    checked += 1
                    correct += text == box["label"]

    args.out.write_text(json.dumps(predictions, indent=1))
    boxes = sum(len(v) for v in predictions.values())
    print(f"Wrote {boxes} predictions for {len(predictions)} photos to {args.out}")
    if checked:
        print(f"On already-labeled boxes: {correct}/{checked} = {correct / checked:.1%} exact match")


if __name__ == "__main__":
    main()
