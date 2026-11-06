"""Train the price-corner detector on the Mac GPU (step 3b).

Setup once, in the same venv as train_crnn.py:
    pip install ultralytics

Usage (after prepare_dataset.py):
    python scripts/lotto/train_detector.py                # ~20-60 min on M1/M2/M3
    python scripts/lotto/train_detector.py --epochs 30    # quick smoke run

It fine-tunes a small YOLO model that was pretrained on everyday photos, so it
starts out already knowing edges and shapes. It learns one thing: "this is a
ticket's price corner". The value ($5, $10, ...) is read afterwards by the
reader from train_crnn.py, which learns digits, so a rare $50 borrows its
"5" and "0" from the common values (a digit unique to one value, like the
"3" of $30, still needs its own examples).

Writes lotto_data/models/corner_detector.pt and prints, for every test photo,
how many corners it found vs. how many you boxed.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import torch
from ultralytics import YOLO


def pick_device() -> str:
    """Prefer the Mac GPU (MPS), then CUDA, then CPU."""
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "0"
    return "cpu"


def count_check(  # noqa: PLR0913
    model: YOLO, data: Path, split: str, *, imgsz: int, conf: float, device: str,
) -> None:
    """Compare found vs. boxed corners per photo of ``split``."""
    images = sorted((data / "yolo" / "images" / split).glob("*.jpg"))
    if not images:
        print(f"No {split} photos yet.")
        return
    exact = off = 0
    for image in images:
        found = len(model.predict(image, imgsz=imgsz, conf=conf, device=device, verbose=False)[0].boxes)
        label_file = data / "yolo" / "labels" / split / f"{image.stem}.txt"
        boxed = sum(1 for line in label_file.read_text().splitlines() if line.strip())
        exact += found == boxed
        off += abs(found - boxed)
        print(f"  {image.stem[:8]}  you {boxed:3d}  model {found:3d}  {'✓' if found == boxed else ''}")
    print(f"{split.upper()}: exact corner count on {exact}/{len(images)} photos, off by {off / len(images):.1f} on average")


def main() -> None:
    """Fine-tune YOLO on the price corners and report counting accuracy."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=Path("lotto_data"))
    parser.add_argument("--model", default="yolo11n.pt", help="starting weights (yolo11s.pt is bigger and slower)")
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--imgsz", type=int, default=1280, help="price corners are small: keep this high")
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--conf", type=float, default=0.35, help="minimum confidence to count a corner")
    args = parser.parse_args()

    data_yaml = args.data / "yolo" / "data.yaml"
    if not data_yaml.exists():
        msg = "No lotto_data/yolo/data.yaml. Run prepare_dataset.py on a labeled export first."
        raise SystemExit(msg)
    device = pick_device()
    print(f"Device: {device}")

    model = YOLO(args.model)
    result = model.train(
        data=str(data_yaml.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        project=str((args.data / "runs").resolve()),
        name="detector",
        exist_ok=True,
        patience=40,
        # Price corners are always top-left and text is never mirrored:
        # flipping would teach the model shapes it never sees in a real photo.
        fliplr=0.0,
        degrees=5.0,
        perspective=0.0005,
        hsv_v=0.5,
        plots=True,
        verbose=False,
    )
    best = Path(result.save_dir) / "weights" / "best.pt"
    out = args.data / "models" / "corner_detector.pt"
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(best, out)
    print(f"Saved best detector to {out}")

    count_check(YOLO(str(out)), args.data, "test", imgsz=args.imgsz, conf=args.conf, device=device)


if __name__ == "__main__":
    main()
