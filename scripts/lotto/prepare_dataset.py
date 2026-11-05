"""Turn a /lotto/export.zip into cropped training images (step 3a, on the Mac).

Usage:
    python scripts/lotto/prepare_dataset.py ~/Downloads/lotto-labeled-20261105.zip

Writes:
    lotto_data/crops/{train,val,test}/<photo>_<box>.png
    lotto_data/{train,val,test}.tsv      # "relative/path.png<TAB>label"
    lotto_data/charset.txt               # every character seen in labels

The output folder is rebuilt from scratch each time, so always run it on the
newest export.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from collections import Counter
from pathlib import Path

from lotto_common import crops_for_entry, default_data_dir, read_manifest

SPLITS = ("train", "val", "test")


def main() -> None:
    """Crop every labeled box and write the split files."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("zip", type=Path, help="export zip downloaded from /lotto (scope=labeled)")
    parser.add_argument("--data", type=Path, default=default_data_dir(), help="output folder (default: lotto_data)")
    parser.add_argument("--pad", type=float, default=0.08, help="margin around each box, as a fraction of its size")
    args = parser.parse_args()

    crops_dir = args.data / "crops"
    if crops_dir.exists():
        shutil.rmtree(crops_dir)
    rows: dict[str, list[str]] = {split: [] for split in SPLITS}
    chars: Counter[str] = Counter()
    lengths: Counter[int] = Counter()

    with zipfile.ZipFile(args.zip) as archive:
        entries = [e for e in read_manifest(archive) if e.labeled]
        for entry in entries:
            split = entry.split if entry.split in SPLITS else "train"
            out_dir = crops_dir / split
            out_dir.mkdir(parents=True, exist_ok=True)
            for index, (box, crop) in enumerate(zip(entry.boxes, crops_for_entry(archive, entry, args.pad), strict=True)):
                label = box.get("label") or ""
                if not label:
                    continue
                path = out_dir / f"{entry.id}_{index}.png"
                crop.save(path)
                rows[split].append(f"{path.relative_to(args.data)}\t{label}")
                chars.update(label)
                lengths[len(label)] += 1

    args.data.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        (args.data / f"{split}.tsv").write_text("\n".join(rows[split]) + ("\n" if rows[split] else ""))
    (args.data / "charset.txt").write_text("".join(sorted(chars)))

    print(f"Photos: {len(entries)}")
    for split in SPLITS:
        print(f"  {split:5s}: {len(rows[split]):5d} numbers")
    print(f"Characters: {''.join(sorted(chars))!r}")
    print(f"Number lengths: {dict(sorted(lengths.items()))}")
    print(f"Open {crops_dir} in Finder and flip through a few crops: they should be tight and upright.")


if __name__ == "__main__":
    main()
