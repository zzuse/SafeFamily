"""Collect and label photos for the lotto ticket-number recognizer.

Workflow (see docs/lotto-training.md):

1. Upload photos at /lotto, from a phone or a computer.
2. Label each one at /lotto/<id>: rotate it upright, draw a box around each
   ticket number, then type the number.
3. Download /lotto/export.zip and train on the Mac (scripts/lotto/).
4. Upload the Mac's predictions.json back to /lotto so that new photos arrive
   pre-filled and labeling becomes "check and correct".

The server only stores and serves data; it does no image processing, so it
needs no GPU and no extra Python packages.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import tempfile
import uuid
import zipfile
from datetime import UTC, date, datetime

from flask import (
    Blueprint,
    Response,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import db, local_tz
from src.safe_family.core.models import LottoPhoto

lotto_bp = Blueprint("lotto", __name__)

PHOTOS_PER_DAY = 2
PER_PAGE = 24
MAX_BOXES = 60
MAX_LABEL_LEN = 20
MIN_BOX_SIZE = 0.002
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
VALID_ROTATIONS = (0, 90, 180, 270)
VALID_SPLITS = ("train", "val", "test")
LABEL_RE = re.compile(r"^[0-9A-Z\-]{1,20}$")

# 70 / 15 / 15 split assigned by calendar day: every photo taken on the same
# day lands in the same split, so near-identical shots of one scene can never
# be in both train and test (that would make the test score look too good).
# Cycling by day also spreads every split over every week, as lighting, games
# and camera angle drift over time.
_SPLIT_CYCLE = ("train",) * 14 + ("val",) * 3 + ("test",) * 3

# Goals counted in labeled numbers (boxes), not photos: one photo of a
# dispenser can hold many ticket numbers.
MILESTONES = (
    {
        "boxes": 60,
        "title": "Baseline check",
        "detail": "A first test set. Run off-the-shelf OCR on it on the Mac "
        "(scripts/lotto/baseline_ocr.py). If it already reads 98%+ correctly, "
        "you may not need to train a model at all.",
    },
    {
        "boxes": 300,
        "title": "First trained model",
        "detail": "Train the small CRNN on the Mac GPU (scripts/lotto/train_crnn.py). "
        "Then upload its predictions so labeling becomes checking.",
    },
    {
        "boxes": 1000,
        "title": "Solid model",
        "detail": "Enough variety (games, lighting, angles) for ~99% per-number accuracy. "
        "Keep adding a few photos a week to catch new ticket designs.",
    },
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def assign_split(day: date) -> str:
    """Return the dataset split for photos uploaded on ``day`` (local date)."""
    return _SPLIT_CYCLE[day.toordinal() % len(_SPLIT_CYCLE)]


def normalize_label(raw: object) -> str | None:
    """Normalize a typed ticket number; return None when it is invalid.

    Spaces are dropped and letters upper-cased. An empty string is valid and
    means "not labeled yet".
    """
    if raw is None:
        return ""
    if not isinstance(raw, str | int):
        return None
    text = re.sub(r"\s+", "", str(raw)).upper()
    if not text:
        return ""
    if len(text) > MAX_LABEL_LEN or not LABEL_RE.match(text):
        return None
    return text


def _as_fraction(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return min(max(number, 0.0), 1.0)


def _clean_box(item: object) -> dict | None:
    """Validate one box dict; return a cleaned copy or None to drop it."""
    if not isinstance(item, dict):
        return None
    coords = [_as_fraction(item.get(key)) for key in ("x", "y", "w", "h")]
    if any(c is None for c in coords):
        return None
    x, y, w, h = coords
    w = min(w, 1.0 - x)
    h = min(h, 1.0 - y)
    if w < MIN_BOX_SIZE or h < MIN_BOX_SIZE:
        return None
    label = normalize_label(item.get("label"))
    if label is None:
        return None
    box = {
        "x": round(x, 5),
        "y": round(y, 5),
        "w": round(w, 5),
        "h": round(h, 5),
        "label": label,
    }
    pred = normalize_label(item.get("pred"))
    if pred:
        box["pred"] = pred
        conf = _as_fraction(item.get("conf"))
        if conf is not None:
            box["conf"] = round(conf, 4)
    return box


def parse_boxes(raw: str | None) -> list[dict]:
    """Parse and validate the boxes JSON posted by the labeling page.

    Raises ValueError when the payload is not a JSON list or has a box with an
    invalid label; boxes with broken geometry are dropped silently.
    """
    try:
        data = json.loads(raw or "[]")
    except (TypeError, ValueError) as exc:
        msg = "Boxes are not valid JSON."
        raise ValueError(msg) from exc
    if not isinstance(data, list):
        msg = "Boxes must be a list."
        raise ValueError(msg)  # noqa: TRY004 - the view reports every bad payload the same way
    if len(data) > MAX_BOXES:
        msg = f"At most {MAX_BOXES} boxes per photo."
        raise ValueError(msg)
    boxes = []
    for item in data:
        if isinstance(item, dict) and normalize_label(item.get("label")) is None:
            msg = f"Invalid number {item.get('label')!r}: use digits, letters or '-' (max {MAX_LABEL_LEN})."
            raise ValueError(msg)
        box = _clean_box(item)
        if box is not None:
            boxes.append(box)
    return boxes


def load_boxes(photo: LottoPhoto) -> list[dict]:
    """Return the stored boxes of a photo, tolerating bad stored data."""
    try:
        data = json.loads(photo.boxes_json or "[]")
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def is_fully_labeled(boxes: list[dict]) -> bool:
    """Return True when there is at least one box and every box has a label."""
    return bool(boxes) and all(box.get("label") for box in boxes)


def compute_progress(photos: list[LottoPhoto], photos_per_day: int = PHOTOS_PER_DAY) -> dict:
    """Summarize labeling progress and estimate days left for each milestone."""
    split_boxes = dict.fromkeys(VALID_SPLITS, 0)
    labeled_photos = 0
    todo_photos = 0
    skipped_photos = 0
    for photo in photos:
        if photo.skipped:
            skipped_photos += 1
            continue
        if photo.labeled_at is None:
            todo_photos += 1
            continue
        labeled_photos += 1
        count = sum(1 for box in load_boxes(photo) if box.get("label"))
        split_boxes[photo.split] = split_boxes.get(photo.split, 0) + count
    labeled_boxes = sum(split_boxes.values())
    boxes_per_photo = labeled_boxes / labeled_photos if labeled_photos else 1.0
    boxes_per_day = max(boxes_per_photo, 1.0) * photos_per_day

    milestones = []
    for goal in MILESTONES:
        remaining = max(goal["boxes"] - labeled_boxes, 0)
        milestones.append(
            {
                **goal,
                "remaining": remaining,
                "done": remaining == 0,
                "percent": min(100, round(100 * labeled_boxes / goal["boxes"])),
                "days_left": math.ceil(remaining / boxes_per_day),
            },
        )
    return {
        "total_photos": len(photos),
        "labeled_photos": labeled_photos,
        "todo_photos": todo_photos,
        "skipped_photos": skipped_photos,
        "labeled_boxes": labeled_boxes,
        "split_boxes": split_boxes,
        "boxes_per_photo": round(boxes_per_photo, 1),
        "photos_per_day": photos_per_day,
        "milestones": milestones,
    }


def _template_from_latest(user_id: str) -> tuple[int, str]:
    """Reuse the latest labeled photo's rotation and box positions (no labels).

    The tickets sit in the same dispenser slots every day, so the boxes
    usually only need a small nudge instead of being drawn from scratch.
    """
    latest = (
        LottoPhoto.query.filter(
            LottoPhoto.user_id == user_id,
            LottoPhoto.labeled_at.isnot(None),
        )
        .order_by(LottoPhoto.labeled_at.desc())
        .first()
    )
    if latest is None:
        return 0, "[]"
    boxes = [
        {key: box[key] for key in ("x", "y", "w", "h")} | {"label": ""}
        for box in load_boxes(latest)
        if all(key in box for key in ("x", "y", "w", "h"))
    ]
    return latest.rotation, json.dumps(boxes)


def _next_todo(user_id: str, exclude_id: str | None = None) -> LottoPhoto | None:
    query = LottoPhoto.query.filter(
        LottoPhoto.user_id == user_id,
        LottoPhoto.labeled_at.is_(None),
        LottoPhoto.skipped.is_(False),
    )
    if exclude_id:
        query = query.filter(LottoPhoto.id != exclude_id)
    return query.order_by(LottoPhoto.created_at.asc()).first()


def _local(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    return ts.replace(tzinfo=UTC).astimezone(local_tz)


def _get_owned(photo_id: str, user_id: str) -> LottoPhoto:
    photo = LottoPhoto.query.filter_by(id=photo_id, user_id=user_id).one_or_none()
    if photo is None:
        abort(404)
    return photo


def _require_user():  # noqa: ANN202 - returns a User or a redirect response
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return None, redirect("/auth/login-ui")
    return user, None


@lotto_bp.get("/lotto")
@login_required
def lotto_home():
    """Dashboard: upload form, progress toward each milestone, photo grid."""
    user, response = _require_user()
    if response:
        return response
    status = request.args.get("status", "todo")
    page = request.args.get("page", 1, type=int)

    all_photos = LottoPhoto.query.filter_by(user_id=user.id).with_entities(
        LottoPhoto.id,
        LottoPhoto.split,
        LottoPhoto.skipped,
        LottoPhoto.labeled_at,
        LottoPhoto.boxes_json,
    ).all()
    progress = compute_progress(all_photos)

    query = LottoPhoto.query.filter_by(user_id=user.id).with_entities(
        LottoPhoto.id,
        LottoPhoto.filename,
        LottoPhoto.split,
        LottoPhoto.skipped,
        LottoPhoto.labeled_at,
        LottoPhoto.rotation,
        LottoPhoto.boxes_json,
        LottoPhoto.created_at,
    )
    if status == "todo":
        query = query.filter(LottoPhoto.labeled_at.is_(None), LottoPhoto.skipped.is_(False))
    elif status == "labeled":
        query = query.filter(LottoPhoto.labeled_at.isnot(None), LottoPhoto.skipped.is_(False))
    elif status == "skipped":
        query = query.filter(LottoPhoto.skipped.is_(True))
    else:
        status = "all"
    pagination = query.order_by(LottoPhoto.created_at.desc()).paginate(
        page=page,
        per_page=PER_PAGE,
        error_out=False,
    )
    cards = [
        {
            "id": row.id,
            "filename": row.filename,
            "split": row.split,
            "skipped": row.skipped,
            "labeled": row.labeled_at is not None,
            "rotation": row.rotation,
            "labels": [box.get("label") or box.get("pred") or "?" for box in load_boxes(row)],
            "created_local": _local(row.created_at),
        }
        for row in pagination.items
    ]
    next_todo = _next_todo(user.id)
    return render_template(
        "lotto/lotto.html",
        progress=progress,
        cards=cards,
        pagination=pagination,
        status=status,
        next_todo_id=next_todo.id if next_todo else None,
    )


@lotto_bp.post("/lotto/upload")
@login_required
def lotto_upload():
    """Store uploaded photos untouched and queue them for labeling."""
    user, response = _require_user()
    if response:
        return response
    files = [f for f in request.files.getlist("photos") if f and f.filename]
    if not files:
        flash("Choose at least one photo.", "warning")
        return redirect(url_for("lotto.lotto_home"))

    rotation, boxes_json = _template_from_latest(user.id)
    added, duplicates, rejected = [], 0, 0
    now = _now()
    split = assign_split(datetime.now(local_tz).date())
    for upload in files:
        content_type = upload.content_type or ""
        data = upload.read()
        if not content_type.startswith("image/") or not data or len(data) > MAX_UPLOAD_BYTES:
            rejected += 1
            continue
        checksum = f"sha256:{hashlib.sha256(data).hexdigest()}"
        if LottoPhoto.query.filter_by(user_id=user.id, checksum=checksum).first():
            duplicates += 1
            continue
        photo = LottoPhoto(
            id=uuid.uuid4().hex,
            user_id=user.id,
            filename=upload.filename,
            content_type=content_type,
            checksum=checksum,
            data=data,
            rotation=rotation,
            boxes_json=boxes_json,
            split=split,
            skipped=False,
            created_at=now,
            updated_at=now,
        )
        db.session.add(photo)
        added.append(photo)
    db.session.commit()

    parts = [f"Uploaded {len(added)} photo(s)."]
    if duplicates:
        parts.append(f"{duplicates} duplicate(s) ignored.")
    if rejected:
        parts.append(f"{rejected} file(s) rejected (not an image, or over 20 MB).")
    flash(" ".join(parts), "success" if added else "warning")
    if added:
        return redirect(url_for("lotto.lotto_label", photo_id=added[0].id))
    return redirect(url_for("lotto.lotto_home"))


@lotto_bp.get("/lotto/<photo_id>")
@login_required
def lotto_label(photo_id: str):
    """Labeling page: rotate, draw boxes, type numbers."""
    user, response = _require_user()
    if response:
        return response
    photo = _get_owned(photo_id, user.id)
    next_todo = _next_todo(user.id, exclude_id=photo.id)
    return render_template(
        "lotto/lotto_label.html",
        photo=photo,
        boxes=load_boxes(photo),
        created_local=_local(photo.created_at),
        next_todo_id=next_todo.id if next_todo else None,
        splits=VALID_SPLITS,
    )


@lotto_bp.post("/lotto/<photo_id>")
@login_required
def lotto_save(photo_id: str):
    """Save rotation, boxes and split; optionally jump to the next photo."""
    user, response = _require_user()
    if response:
        return response
    photo = _get_owned(photo_id, user.id)
    action = request.form.get("action", "save")

    if action in ("skip", "unskip"):
        photo.skipped = action == "skip"
        photo.updated_at = _now()
        db.session.commit()
        flash("Photo skipped (kept, but left out of the dataset)." if photo.skipped else "Photo restored.", "info")
        return _after_save(user.id, photo, go_next=photo.skipped)

    rotation = request.form.get("rotation", 0, type=int)
    if rotation not in VALID_ROTATIONS:
        flash("Rotation must be 0, 90, 180 or 270.", "danger")
        return redirect(url_for("lotto.lotto_label", photo_id=photo.id))
    try:
        boxes = parse_boxes(request.form.get("boxes"))
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("lotto.lotto_label", photo_id=photo.id))
    split = request.form.get("split", photo.split)
    if split in VALID_SPLITS:
        photo.split = split

    photo.rotation = rotation
    photo.boxes_json = json.dumps(boxes)
    photo.updated_at = _now()
    if is_fully_labeled(boxes):
        photo.labeled_at = photo.labeled_at or photo.updated_at
        flash(f"Saved {len(boxes)} number(s).", "success")
    else:
        photo.labeled_at = None
        flash("Saved as draft: draw at least one box and type every number to finish it.", "warning")
    db.session.commit()
    return _after_save(user.id, photo, go_next=action == "save_next" and photo.labeled_at is not None)


def _after_save(user_id: str, photo: LottoPhoto, *, go_next: bool) -> Response:
    if go_next:
        nxt = _next_todo(user_id, exclude_id=photo.id)
        if nxt is not None:
            return redirect(url_for("lotto.lotto_label", photo_id=nxt.id))
        flash("All photos are labeled. Nice work!", "success")
        return redirect(url_for("lotto.lotto_home"))
    return redirect(url_for("lotto.lotto_label", photo_id=photo.id))


@lotto_bp.post("/lotto/<photo_id>/delete")
@login_required
def lotto_delete(photo_id: str):
    """Delete a photo for good (use Skip to keep it but leave it out)."""
    user, response = _require_user()
    if response:
        return response
    photo = _get_owned(photo_id, user.id)
    db.session.delete(photo)
    db.session.commit()
    flash("Photo deleted.", "success")
    return redirect(url_for("lotto.lotto_home"))


@lotto_bp.get("/lotto/<photo_id>/image")
@login_required
def lotto_image(photo_id: str):
    """Serve the original uploaded image."""
    user, response = _require_user()
    if response:
        return response
    photo = _get_owned(photo_id, user.id)
    return send_file(
        io.BytesIO(photo.data),
        mimetype=photo.content_type,
        download_name=photo.filename,
        max_age=86400,
    )


def _image_ext(photo: LottoPhoto) -> str:
    ext = photo.content_type.split("/", 1)[-1].lower()
    return {"jpeg": "jpg", "svg+xml": "svg"}.get(ext, ext) or "bin"


def build_manifest_entry(photo: LottoPhoto, file_name: str) -> dict:
    """Describe one photo for the training scripts (one JSON line)."""
    return {
        "id": photo.id,
        "file": file_name,
        "original_filename": photo.filename,
        "rotation": photo.rotation,
        "split": photo.split,
        "skipped": photo.skipped,
        "labeled": photo.labeled_at is not None,
        "boxes": load_boxes(photo),
        "created_at": photo.created_at.isoformat() if photo.created_at else None,
    }


@lotto_bp.get("/lotto/export.zip")
@login_required
def lotto_export():
    """Download the dataset: original images plus manifest.jsonl.

    ``?scope=labeled`` (default) exports finished photos for training;
    ``?scope=all`` also exports unlabeled ones so the Mac can pre-label them.
    """
    user, response = _require_user()
    if response:
        return response
    scope = request.args.get("scope", "labeled")
    query = LottoPhoto.query.filter_by(user_id=user.id, skipped=False)
    if scope != "all":
        scope = "labeled"
        query = query.filter(LottoPhoto.labeled_at.isnot(None))
    photos = query.order_by(LottoPhoto.created_at.asc()).all()

    spool = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)  # noqa: SIM115 - send_file closes it
    manifest_lines = []
    with zipfile.ZipFile(spool, "w") as archive:
        for photo in photos:
            file_name = f"images/{photo.id}.{_image_ext(photo)}"
            # Photos are already compressed; storing avoids burning CPU for ~0 gain.
            archive.writestr(file_name, photo.data, compress_type=zipfile.ZIP_STORED)
            manifest_lines.append(json.dumps(build_manifest_entry(photo, file_name)))
        archive.writestr(
            "manifest.jsonl",
            "\n".join(manifest_lines) + ("\n" if manifest_lines else ""),
            compress_type=zipfile.ZIP_DEFLATED,
        )
    spool.seek(0)
    stamp = datetime.now(local_tz).strftime("%Y%m%d")
    return send_file(
        spool,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"lotto-{scope}-{stamp}.zip",
    )


def apply_predictions(photo: LottoPhoto, predictions: object) -> bool:
    """Attach model predictions to a photo's boxes, by box index.

    ``predictions`` is a list like ``[{"text": "023", "conf": 0.97}, ...]``.
    Human labels are never overwritten. Returns True when something changed.
    """
    if not isinstance(predictions, list):
        return False
    boxes = load_boxes(photo)
    changed = False
    for box, pred in zip(boxes, predictions, strict=False):
        if not isinstance(pred, dict):
            continue
        text = normalize_label(pred.get("text"))
        if not text:
            continue
        box["pred"] = text
        conf = _as_fraction(pred.get("conf"))
        if conf is not None:
            box["conf"] = round(conf, 4)
        else:
            box.pop("conf", None)
        changed = True
    if changed:
        photo.boxes_json = json.dumps(boxes)
        photo.updated_at = _now()
    return changed


@lotto_bp.post("/lotto/predictions")
@login_required
def lotto_predictions():
    """Import predictions.json produced by scripts/lotto/predict.py."""
    user, response = _require_user()
    if response:
        return response
    upload = request.files.get("predictions")
    if upload is None or not upload.filename:
        flash("Choose the predictions.json file made by predict.py.", "warning")
        return redirect(url_for("lotto.lotto_home"))
    try:
        payload = json.loads(upload.read().decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        flash("predictions.json is not valid JSON.", "danger")
        return redirect(url_for("lotto.lotto_home"))
    if not isinstance(payload, dict):
        flash("predictions.json must map photo ids to lists of predictions.", "danger")
        return redirect(url_for("lotto.lotto_home"))

    photos = LottoPhoto.query.filter(
        LottoPhoto.user_id == user.id,
        LottoPhoto.id.in_(list(payload.keys())),
    ).all()
    updated = sum(1 for photo in photos if apply_predictions(photo, payload.get(photo.id)))
    db.session.commit()
    flash(f"Predictions applied to {updated} photo(s).", "success")
    return redirect(url_for("lotto.lotto_home"))
