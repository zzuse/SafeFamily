"""Small CRNN + CTC text recognizer for ticket numbers (needs PyTorch).

A CNN turns a 32 x 128 grayscale crop into 32 vertical slices, a BiLSTM reads
them left to right, and CTC lets it output a variable-length string without
per-digit boxes. ~1M parameters: trains in minutes on an Apple-silicon GPU
(MPS), and runs fast enough on a plain server CPU.
"""

from __future__ import annotations

import torch
from PIL import Image, ImageOps
from torch import nn

IMG_H = 32
IMG_W = 128


def pick_device() -> torch.device:
    """Prefer the Mac GPU (MPS), then CUDA, then CPU."""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def to_tensor(image: Image.Image) -> torch.Tensor:
    """Grayscale, keep aspect ratio at height 32, pad right to width 128."""
    image = ImageOps.autocontrast(image.convert("L"))
    width = max(1, min(IMG_W, round(image.width * IMG_H / max(image.height, 1))))
    image = image.resize((width, IMG_H), Image.Resampling.BILINEAR)
    canvas = Image.new("L", (IMG_W, IMG_H), color=int(sum(image.getdata()) / (width * IMG_H)))
    canvas.paste(image, (0, 0))
    data = torch.frombuffer(bytearray(canvas.tobytes()), dtype=torch.uint8).float()
    return (data.view(1, IMG_H, IMG_W) / 255.0 - 0.5) / 0.5


def _block(cin: int, cout: int, pool: tuple[int, int]) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
        nn.MaxPool2d(pool),
    )


class CRNN(nn.Module):
    """CNN feature extractor + BiLSTM + per-slice classifier (blank = 0)."""

    def __init__(self, num_chars: int) -> None:
        """Build the network for ``num_chars`` characters plus the CTC blank."""
        super().__init__()
        self.cnn = nn.Sequential(
            _block(1, 32, (2, 2)),  # 16 x 64
            _block(32, 64, (2, 2)),  # 8 x 32
            _block(64, 128, (2, 1)),  # 4 x 32
            _block(128, 128, (4, 1)),  # 1 x 32
            nn.Dropout(0.2),
        )
        self.rnn = nn.LSTM(128, 128, num_layers=2, bidirectional=True, batch_first=True, dropout=0.2)
        self.fc = nn.Linear(256, num_chars + 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Return log-probabilities shaped (time=32, batch, classes) for CTC."""
        features = self.cnn(x).squeeze(2).permute(0, 2, 1)  # B, T, C
        out, _ = self.rnn(features)
        return self.fc(out).log_softmax(2).permute(1, 0, 2)


def greedy_decode(log_probs: torch.Tensor, charset: str) -> list[tuple[str, float]]:
    """Best-path CTC decoding; confidence = product of the kept steps' probs."""
    probs, best = log_probs.detach().float().cpu().exp().max(2)  # T, B
    results = []
    for b in range(best.shape[1]):
        text, conf, prev = [], 1.0, 0
        for t in range(best.shape[0]):
            idx = int(best[t, b])
            if idx not in (0, prev):
                text.append(charset[idx - 1])
                conf *= float(probs[t, b])
            prev = idx
        results.append(("".join(text), conf if text else 0.0))
    return results


def save_checkpoint(path: str, model: CRNN, charset: str, meta: dict) -> None:
    """Save weights plus everything predict.py needs to rebuild the model."""
    torch.save({"state_dict": model.state_dict(), "charset": charset, "meta": meta}, path)


def load_checkpoint(path: str, device: torch.device) -> tuple[CRNN, str]:
    """Load a model saved by train_crnn.py."""
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = CRNN(len(ckpt["charset"]))
    model.load_state_dict(ckpt["state_dict"])
    return model.to(device).eval(), ckpt["charset"]
