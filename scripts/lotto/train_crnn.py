"""Train the ticket-number recognizer on the Mac GPU (step 3c).

Setup once (Apple-silicon Mac, Python 3.11+):
    python3 -m venv ~/lotto-venv && source ~/lotto-venv/bin/activate
    pip install torch torchvision pillow

Usage (after prepare_dataset.py):
    python scripts/lotto/train_crnn.py                 # ~5-20 min on M1/M2/M3
    python scripts/lotto/train_crnn.py --epochs 60     # quicker smoke run

Writes lotto_data/models/lotto_crnn.pt (best on val) and prints test accuracy.
Training from the same data twice gives slightly different results; compare
runs by the final test score, never by the train score.
"""

from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

import torch
from lotto_model import CRNN, greedy_decode, pick_device, save_checkpoint, to_tensor
from PIL import Image, ImageFilter
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision.transforms import v2 as T  # noqa: N812 - conventional alias


def read_rows(data: Path, split: str) -> list[tuple[Path, str]]:
    """Read ``split``.tsv written by prepare_dataset.py."""
    path = data / f"{split}.tsv"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rel, label = line.split("\t")
            rows.append((data / rel, label))
    return rows


BLUR_PROBABILITY = 0.3


class RandomBlur:
    """Simulate a slightly out-of-focus phone photo."""

    def __call__(self, image: Image.Image) -> Image.Image:
        """Blur with probability 0.3."""
        if random.random() < BLUR_PROBABILITY:  # noqa: S311 - augmentation, not crypto
            return image.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.3, 1.2)))  # noqa: S311
        return image


# Real-world variation a few hundred photos can't cover on their own:
# small tilt / perspective, framing that is a bit off, lighting and blur.
AUGMENT = T.Compose(
    [
        T.RandomAffine(degrees=4, translate=(0.04, 0.08), scale=(0.9, 1.1), shear=(-8, 8, -3, 3), fill=128),
        T.RandomPerspective(distortion_scale=0.15, p=0.4, fill=128),
        T.ColorJitter(brightness=0.4, contrast=0.4),
        RandomBlur(),
    ],
)


class CropDataset(Dataset):
    """Labeled crops; ``length`` > len(rows) re-samples with fresh augmentation."""

    def __init__(self, rows: list[tuple[Path, str]], charset: str, *, augment: bool, length: int | None = None) -> None:
        """Load all crops into memory (they are tiny)."""
        self.images = [Image.open(path).convert("L") for path, _ in rows]
        self.labels = [label for _, label in rows]
        self.index = {ch: i + 1 for i, ch in enumerate(charset)}
        self.augment = augment
        self.length = length or len(rows)

    def __len__(self) -> int:
        """Return the number of samples per epoch."""
        return self.length

    def __getitem__(self, i: int) -> tuple[torch.Tensor, torch.Tensor, str]:
        """Return (image tensor, encoded label, label text)."""
        i %= len(self.images)
        image = self.images[i]
        if self.augment:
            image = AUGMENT(image)
        label = self.labels[i]
        return to_tensor(image), torch.tensor([self.index[c] for c in label], dtype=torch.long), label


def collate(batch: list) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, list[str]]:
    """Stack images; concatenate targets the way CTCLoss expects."""
    images, targets, texts = zip(*batch, strict=True)
    lengths = torch.tensor([len(t) for t in targets], dtype=torch.long)
    return torch.stack(images), torch.cat(targets), lengths, list(texts)


def evaluate(model: CRNN, loader: DataLoader, charset: str, device: torch.device) -> tuple[float, list]:
    """Exact-match accuracy and the list of mistakes."""
    model.eval()
    correct, total, misses = 0, 0, []
    with torch.no_grad():
        for images, _targets, _lengths, texts in loader:
            for (guess, conf), truth in zip(greedy_decode(model(images.to(device)), charset), texts, strict=True):
                total += 1
                if guess == truth:
                    correct += 1
                else:
                    misses.append((truth, guess, conf))
    return (correct / total if total else 0.0), misses


def warn_missing_values(train_rows: list, others: dict[str, list]) -> None:
    """Warn when val/test lack a value that train has: their score can't judge it."""
    train_values = {label for _, label in train_rows}
    for name, rows in others.items():
        missing = sorted(train_values - {label for _, label in rows}, key=lambda v: (len(v), v))
        if rows and missing:
            print(
                f"WARNING: {name} has no {', '.join('$' + v for v in missing)}: its score can't show whether "
                "those values are read right. Label more photos with them.",
            )


def main() -> None:  # noqa: PLR0915 - a linear training script reads best top to bottom
    """Train, keep the best checkpoint on val, report on test."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, default=Path("lotto_data"))
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument("--samples-per-epoch", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = pick_device()
    print(f"Device: {device}")

    train_rows, val_rows, test_rows = (read_rows(args.data, s) for s in ("train", "val", "test"))
    if not train_rows:
        msg = "No training rows. Run prepare_dataset.py on a labeled export first."
        raise SystemExit(msg)
    if not val_rows:
        print("No val rows yet: using train rows for model selection (scores will look too good).")
        val_rows = train_rows
    charset = "".join(sorted({c for _, label in train_rows + val_rows + test_rows for c in label}))
    print(f"train {len(train_rows)} · val {len(val_rows)} · test {len(test_rows)} · charset {charset!r}")
    warn_missing_values(train_rows, {"val": val_rows, "test": test_rows})

    train_loader = DataLoader(
        CropDataset(train_rows, charset, augment=True, length=max(args.samples_per_epoch, len(train_rows))),
        batch_size=args.batch,
        shuffle=True,
        collate_fn=collate,
    )
    val_loader = DataLoader(CropDataset(val_rows, charset, augment=False), batch_size=128, collate_fn=collate)

    model = CRNN(len(charset)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=args.lr,
        total_steps=args.epochs * len(train_loader),
    )
    ctc = nn.CTCLoss(blank=0, zero_infinity=True)
    out_dir = args.data / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    best_path = out_dir / "lotto_crnn.pt"
    best_acc, best_epoch = -1.0, 0
    started = time.time()

    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for images, targets, target_lengths, _texts in train_loader:
            log_probs = model(images.to(device))
            # CTC loss is not implemented on MPS: compute it on the CPU.
            log_probs_cpu = log_probs.float().cpu()
            input_lengths = torch.full((images.shape[0],), log_probs_cpu.shape[0], dtype=torch.long)
            loss = ctc(log_probs_cpu, targets, input_lengths, target_lengths)
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            scheduler.step()
            total_loss += loss.item()
        val_acc, _ = evaluate(model, val_loader, charset, device)
        # ">=": on a tie keep the later, longer-trained model. A small val set
        # can hit 100% early, before rare values in train are learned.
        if val_acc >= best_acc:
            best_acc, best_epoch = val_acc, epoch
            save_checkpoint(str(best_path), model, charset, {"epoch": epoch, "val_acc": val_acc})
        if epoch == 1 or epoch % 10 == 0 or epoch == args.epochs:
            print(
                f"epoch {epoch:4d}  loss {total_loss / len(train_loader):.4f}  "
                f"val {val_acc:.1%}  best {best_acc:.1%}@{best_epoch}  {time.time() - started:.0f}s",
            )

    print(f"Saved best model (val {best_acc:.1%}, epoch {best_epoch}) to {best_path}")
    if test_rows:
        from lotto_model import load_checkpoint  # noqa: PLC0415

        model, charset = load_checkpoint(str(best_path), device)
        test_loader = DataLoader(CropDataset(test_rows, charset, augment=False), batch_size=128, collate_fn=collate)
        test_acc, misses = evaluate(model, test_loader, charset, device)
        print(f"TEST accuracy: {test_acc:.1%} ({len(test_rows) - len(misses)}/{len(test_rows)})")
        for truth, guess, conf in misses[:30]:
            print(f"  label={truth!r} model={guess!r} conf={conf:.2f}")


if __name__ == "__main__":
    main()
