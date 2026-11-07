"""Tests for the lotto ticket-number dataset pages."""

import io
import json
import zipfile
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask_jwt_extended import create_access_token

from src.safe_family.core.extensions import db
from src.safe_family.core.models import LottoPhoto, User
from src.safe_family.lotto import lotto

JPEG = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


def _make_user(user_id, username):
    user = User(id=user_id, username=username, email=f"{username}@example.com", role="user")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()
    return user


def _login(app, client, user_id):
    with app.app_context():
        token = create_access_token(identity=user_id)
    with client.session_transaction() as sess:
        sess["access_token"] = token


def _make_photo(  # noqa: PLR0913
    user_id, *, boxes=(), labeled=False, skipped=False, split="train", data=JPEG, created=None, model=None,
):
    now = created or datetime(2026, 11, 1, 10, 0, 0)
    photo = LottoPhoto(
        user_id=user_id,
        filename="t.jpg",
        content_type="image/jpeg",
        checksum=f"sha256:{hash((user_id, data, now))}",
        data=data,
        rotation=0,
        boxes_json=json.dumps(list(boxes)),
        model_json=None if model is None else json.dumps(model),
        split=split,
        skipped=skipped,
        labeled_at=now if labeled else None,
        created_at=now,
        updated_at=now,
    )
    db.session.add(photo)
    db.session.commit()
    return photo.id


@pytest.fixture
def user_client(notesync_app, notesync_client):
    _make_user("admin", "alice")
    _login(notesync_app, notesync_client, "admin")
    return notesync_client


BOX = {"x": 0.1, "y": 0.1, "w": 0.2, "h": 0.1, "label": "007"}


# ---- pure helpers ---------------------------------------------------------


def test_assign_split_is_70_15_15_by_day():
    start = date(2026, 11, 1)
    splits = [lotto.assign_split(start + timedelta(days=i)) for i in range(20)]
    assert splits.count("train") == 14
    assert splits.count("val") == 3
    assert splits.count("test") == 3
    assert lotto.assign_split(start + timedelta(days=20)) == lotto.assign_split(start)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        ("", ""),
        ("  0 07 ", "007"),
        ("ab-12", "AB-12"),
        (42, "42"),
        ("12.5", None),
        ("1" * 21, None),
        (["1"], None),
    ],
)
def test_normalize_label(raw, expected):
    assert lotto.normalize_label(raw) == expected


def test_parse_boxes_cleans_and_clamps():
    boxes = lotto.parse_boxes(
        json.dumps(
            [
                {"x": 0.9, "y": -1, "w": 0.5, "h": 0.2, "label": " 12 ", "pred": "12", "conf": 1.7},
                {"x": 0.5, "y": 0.5, "w": 0.0001, "h": 0.2, "label": "1"},  # too thin: dropped
                {"x": "a", "y": 0, "w": 0.1, "h": 0.1, "label": "1"},  # bad coords: dropped
                {"x": True, "y": 0, "w": 0.1, "h": 0.1, "label": "1"},  # bool is not a number
                {"x": float("nan"), "y": 0, "w": 0.1, "h": 0.1, "label": "1"},
                "not-a-box",
                {"x": 0, "y": 0, "w": 0.1, "h": 0.1, "label": "", "pred": "bad pred!"},
            ],
        ),
    )
    assert boxes == [
        {"x": 0.9, "y": 0.0, "w": 0.1, "h": 0.2, "label": "12", "pred": "12", "conf": 1.0},
        {"x": 0.0, "y": 0.0, "w": 0.1, "h": 0.1, "label": ""},
    ]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("{nope", "not valid JSON"),
        ('{"x": 1}', "must be a list"),
        (json.dumps([BOX] * (lotto.MAX_BOXES + 1)), "At most"),
        (json.dumps([{**BOX, "label": "1.5"}]), "Invalid number"),
    ],
)
def test_parse_boxes_rejects(raw, message):
    with pytest.raises(ValueError, match=message):
        lotto.parse_boxes(raw)


def test_parse_boxes_empty():
    assert lotto.parse_boxes(None) == []


def test_load_boxes_tolerates_bad_data():
    assert lotto.load_boxes(SimpleNamespace(boxes_json="{bad")) == []
    assert lotto.load_boxes(SimpleNamespace(boxes_json='{"a": 1}')) == []
    assert lotto.load_boxes(SimpleNamespace(boxes_json=None)) == []


def test_is_fully_labeled():
    assert not lotto.is_fully_labeled([])
    assert not lotto.is_fully_labeled([BOX, {**BOX, "label": ""}])
    assert lotto.is_fully_labeled([BOX])


def _row(*, split="train", skipped=False, labeled=True, values=("5",), model=None):
    return SimpleNamespace(
        split=split,
        skipped=skipped,
        labeled_at=datetime(2026, 1, 1) if labeled else None,
        boxes_json=json.dumps([{**BOX, "label": v} for v in values]),
        model_json=None if model is None else json.dumps([{**BOX, "text": v} for v in model]),
    )


def test_tally_and_format():
    boxes = [{"label": "10"}, {"label": "5"}, {"label": "5"}, {"label": ""}, {"label": "X"}, "junk"]
    counts = lotto.tally(boxes)
    assert list(counts.items()) == [("5", 2), ("10", 1), ("X", 1)]
    assert lotto.format_tally(counts) == "$5×2 · $10×1 · X×1"  # noqa: RUF001
    assert lotto.compare_counts({"5": 3, "10": 1}, {"5": 2, "20": 1}) == 3


def test_load_model_boxes():
    assert lotto.load_model_boxes(SimpleNamespace(model_json=None)) is None
    assert lotto.load_model_boxes(SimpleNamespace(model_json="{bad")) is None
    assert lotto.load_model_boxes(SimpleNamespace(model_json='{"a": 1}')) is None
    assert lotto.load_model_boxes(SimpleNamespace(model_json="[]")) == []


def test_compute_progress_counts_backlog_and_eta():
    rows = [
        _row(values=("5", "5", "10", "50"), model=("5", "5", "10", "50")),
        _row(split="test", values=("5", "20"), model=("5",)),
        _row(labeled=False),
        _row(labeled=False),
        _row(skipped=True),
    ]
    progress = lotto.compute_progress(rows, photos_per_day=2)
    assert progress["labeled_boxes"] == 6
    assert progress["split_boxes"] == {"train": 4, "val": 0, "test": 2}
    assert progress["labeled_photos"] == 2
    assert progress["todo_photos"] == 2
    assert progress["skipped_photos"] == 1
    assert progress["boxes_per_photo"] == 3.0
    assert progress["value_counts"] == {"5": 3, "10": 1, "20": 1, "50": 1}
    assert progress["rare_values"] == ["5", "10", "20", "50"]
    assert progress["model_checked"] == 2
    assert progress["model_exact"] == 1
    assert progress["model_off_by"] == 0.5
    first = progress["milestones"][0]
    # 10 - 2 labeled = 8 photos: 2 already uploaded, 6 new at 2/day = 3 days.
    assert first["remaining"] == 8
    assert first["from_backlog"] == 2
    assert first["to_take"] == 6
    assert first["days_left"] == 3
    assert first["percent"] == 20
    assert not first["done"]


def test_compute_progress_backlog_covers_goal():
    progress = lotto.compute_progress([_row(labeled=False)] * 12, photos_per_day=2)
    first = progress["milestones"][0]
    assert first["from_backlog"] == 10
    assert first["to_take"] == 0
    assert first["days_left"] == 0
    assert progress["boxes_per_photo"] == 0
    assert progress["model_checked"] == 0


def test_compute_progress_done_milestone():
    progress = lotto.compute_progress([_row()] * 10)
    assert progress["milestones"][0]["done"]
    assert progress["milestones"][0]["days_left"] == 0


def test_clean_model_boxes():
    assert lotto.clean_model_boxes("nope") == []
    boxes = lotto.clean_model_boxes(
        [
            {"x": 0.1, "y": 0.2, "w": 0.05, "h": 0.04, "text": "$5", "conf": 0.9},
            {"x": 0.1, "y": 0.2, "w": 0.05, "h": 0.04, "text": "bad!"},
            {"x": "a", "y": 0, "w": 0.1, "h": 0.1},
            "junk",
        ],
    )
    assert boxes == [
        {"x": 0.1, "y": 0.2, "w": 0.05, "h": 0.04, "text": "", "conf": 0.9},
        {"x": 0.1, "y": 0.2, "w": 0.05, "h": 0.04, "text": ""},
    ]
    good = lotto.clean_model_boxes([{"x": 0, "y": 0, "w": 0.1, "h": 0.1, "text": "10"}])
    assert good[0]["text"] == "10"


PRED = {"boxes": [{"x": 0.3, "y": 0.3, "w": 0.05, "h": 0.04, "text": "20", "conf": 0.8}, {"x": 0.5, "y": 0.5, "w": 0.05, "h": 0.04, "text": ""}]}


def test_apply_predictions_prefills_unlabeled_photo(notesync_app):
    photo = db.session.get(LottoPhoto, _make_photo("admin", boxes=[{**BOX, "label": ""}]))
    assert lotto.apply_predictions(photo, PRED)
    assert json.loads(photo.boxes_json) == [
        {"x": 0.3, "y": 0.3, "w": 0.05, "h": 0.04, "label": "", "pred": "20", "conf": 0.8},
        {"x": 0.5, "y": 0.5, "w": 0.05, "h": 0.04, "label": ""},
    ]
    assert len(json.loads(photo.model_json)) == 2
    assert not lotto.apply_predictions(photo, ["old", "format"])


def test_apply_predictions_never_overwrites_labels(notesync_app):
    labeled = db.session.get(LottoPhoto, _make_photo("admin", boxes=[BOX], labeled=True))
    draft = db.session.get(LottoPhoto, _make_photo("admin", boxes=[BOX, {**BOX, "label": ""}], data=b"d"))
    for photo in (labeled, draft):
        before = photo.boxes_json
        assert lotto.apply_predictions(photo, PRED)
        assert photo.boxes_json == before
        assert json.loads(photo.model_json)[0]["text"] == "20"


# ---- routes -----------------------------------------------------------------


def test_lotto_requires_login(notesync_client):
    response = notesync_client.get("/lotto")
    assert response.status_code == 302
    assert "/auth/login-ui" in response.headers["Location"]


def test_lotto_home_renders_progress_and_filters(user_client):
    _make_photo("admin", boxes=[BOX], labeled=True)
    _make_photo("admin", data=b"other", created=datetime(2026, 11, 2))
    _make_photo("admin", data=b"skipped", skipped=True)
    _make_photo("u2", boxes=[{**BOX, "label": "424242"}], labeled=True, data=b"x")

    page = user_client.get("/lotto").get_data(as_text=True)
    assert "Lotto ticket counter" in page
    assert "Label next (1 waiting)" in page
    # 10 - 1 labeled = 9 photos: 1 waiting + 8 new at 4/day = 2 days.
    assert "label 1 waiting photo(s)" in page
    assert "~2 day(s) of new photos" in page
    assert "$007" in page

    labeled = user_client.get("/lotto?status=labeled").get_data(as_text=True)
    assert "You: 1 · $007×1" in labeled  # noqa: RUF001
    assert "424242" not in labeled
    assert "skipped" in user_client.get("/lotto?status=skipped").get_data(as_text=True)
    assert user_client.get("/lotto?status=all").status_code == 200


def test_upload_stores_photos_and_dedupes(user_client):
    _make_photo("admin", boxes=[BOX], labeled=True, data=b"old")
    response = user_client.post(
        "/lotto/upload",
        data={
            "photos": [
                (io.BytesIO(JPEG), "a.jpg", "image/jpeg"),
                (io.BytesIO(JPEG), "dup.jpg", "image/jpeg"),
                (io.BytesIO(b"text"), "notes.txt", "text/plain"),
            ],
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    new = LottoPhoto.query.filter_by(filename="a.jpg").one()
    assert response.headers["Location"].endswith(f"/lotto/{new.id}")
    assert new.data == JPEG
    assert new.split in lotto.VALID_SPLITS
    # Ticket positions change daily: new photos start without boxes.
    assert json.loads(new.boxes_json) == []
    assert new.rotation == 0
    assert LottoPhoto.query.count() == 2


def test_home_cards_show_model_comparison(user_client):
    _make_photo(
        "admin",
        boxes=[{**BOX, "label": "5"}, {**BOX, "label": "10"}],
        labeled=True,
        model=[{**BOX, "text": "5"}, {**BOX, "text": "10"}],
    )
    _make_photo("admin", boxes=[{**BOX, "label": "5"}], labeled=True, data=b"2", model=[])
    _make_photo("admin", boxes=[{**BOX, "label": ""}], data=b"3")
    page = user_client.get("/lotto?status=all").get_data(as_text=True)
    assert "Model: 2 · $5×1 · $10×1" in page  # noqa: RUF001
    assert "✓" in page
    assert "off by 1" in page
    assert "draft · 1 boxes" in page
    assert "the count was exactly" in page


HEIC = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 32


@pytest.mark.parametrize(
    ("data", "expected"),
    [(JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp"), (HEIC, None), (b"GIF89a", None), (b"", None)],
)
def test_sniff_image_type(data, expected):
    assert lotto.sniff_image_type(data) == expected


def test_is_heif():
    assert lotto.is_heif(HEIC)
    assert lotto.is_heif(b"\x00\x00\x00\x1cftypmif1")
    assert not lotto.is_heif(JPEG)
    assert not lotto.is_heif(b"\x00\x00\x00\x18ftypisom")  # an MP4 video


def test_upload_rejects_heic_and_trusts_bytes_not_declared_type(user_client):
    response = user_client.post(
        "/lotto/upload",
        data={
            "photos": [
                (io.BytesIO(HEIC), "IMG_0001.HEIC", "image/heic"),
                # Declared HEIC but really a PNG (already converted): accepted as PNG.
                (io.BytesIO(PNG), "IMG_0002.HEIC", "image/heic"),
                # Declared JPEG but really HEIC: still refused.
                (io.BytesIO(HEIC + b"x"), "IMG_0003.jpg", "image/jpeg"),
                (io.BytesIO(b"GIF89a-not-allowed"), "a.gif", "image/gif"),
            ],
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)
    assert "Uploaded 1 photo(s)." in page
    assert "2 HEIC/HEIF photo(s) rejected" in page
    assert "1 file(s) rejected (not a JPEG, PNG or WebP photo" in page
    photo = LottoPhoto.query.one()
    assert photo.content_type == "image/png"
    assert photo.data == PNG


def test_upload_message():
    assert lotto.upload_message(2, 0, 0, 0) == "Uploaded 2 photo(s)."
    message = lotto.upload_message(0, 1, 1, 1)
    assert "1 duplicate(s) ignored." in message
    assert "Most Compatible" in message


def test_upload_without_files_or_only_duplicates(user_client):
    response = user_client.post("/lotto/upload", data={}, content_type="multipart/form-data")
    assert response.headers["Location"].endswith("/lotto")
    _make_photo("admin", data=JPEG)
    LottoPhoto.query.update({"checksum": "sha256:" + __import__("hashlib").sha256(JPEG).hexdigest()})
    db.session.commit()
    response = user_client.post(
        "/lotto/upload",
        data={"photos": [(io.BytesIO(JPEG), "a.jpg", "image/jpeg")]},
        content_type="multipart/form-data",
    )
    assert response.headers["Location"].endswith("/lotto")
    assert LottoPhoto.query.count() == 1


def test_label_page_and_ownership(user_client):
    own = _make_photo("admin", boxes=[BOX])
    other = _make_photo("u2", data=b"x")
    next_id = _make_photo("admin", data=b"y", created=datetime(2026, 11, 3))
    page = user_client.get(f"/lotto/{own}").get_data(as_text=True)
    assert "Value for new boxes" in page
    assert all(f'data-value="{v}"' in page for v in lotto.TICKET_VALUES)
    assert '"label": "007"' in page
    assert f"/lotto/{next_id}" in page
    assert user_client.get(f"/lotto/{other}").status_code == 404
    assert user_client.get(f"/lotto/{other}/image").status_code == 404
    image = user_client.get(f"/lotto/{own}/image")
    assert image.data == JPEG
    assert image.mimetype == "image/jpeg"


def test_save_complete_labels_and_go_next(user_client):
    first = _make_photo("admin")
    second = _make_photo("admin", data=b"2", created=datetime(2026, 11, 2))
    response = user_client.post(
        f"/lotto/{first}",
        data={"rotation": "90", "boxes": json.dumps([BOX]), "split": "test", "action": "save_next"},
    )
    assert response.headers["Location"].endswith(f"/lotto/{second}")
    photo = db.session.get(LottoPhoto, first)
    assert photo.rotation == 90
    assert photo.split == "test"
    assert photo.labeled_at is not None
    assert json.loads(photo.boxes_json)[0]["label"] == "007"


def test_save_last_photo_returns_home(user_client):
    only = _make_photo("admin")
    response = user_client.post(
        f"/lotto/{only}",
        data={"rotation": "0", "boxes": json.dumps([BOX]), "split": "bogus", "action": "save_next"},
    )
    assert response.headers["Location"].endswith("/lotto")
    assert db.session.get(LottoPhoto, only).split == "train"


def test_save_incomplete_is_a_draft(user_client):
    photo_id = _make_photo("admin", boxes=[BOX], labeled=True)
    response = user_client.post(
        f"/lotto/{photo_id}",
        data={"rotation": "0", "boxes": json.dumps([{**BOX, "label": ""}]), "action": "save_next"},
    )
    assert response.headers["Location"].endswith(f"/lotto/{photo_id}")
    assert db.session.get(LottoPhoto, photo_id).labeled_at is None


@pytest.mark.parametrize(
    "form",
    [
        {"rotation": "45", "boxes": "[]"},
        {"rotation": "0", "boxes": "{bad"},
    ],
)
def test_save_rejects_bad_input(user_client, form):
    photo_id = _make_photo("admin", boxes=[BOX])
    response = user_client.post(f"/lotto/{photo_id}", data={**form, "action": "save"})
    assert response.headers["Location"].endswith(f"/lotto/{photo_id}")
    assert json.loads(db.session.get(LottoPhoto, photo_id).boxes_json) == [BOX]


def test_skip_and_unskip(user_client):
    photo_id = _make_photo("admin")
    response = user_client.post(f"/lotto/{photo_id}", data={"action": "skip"})
    assert response.headers["Location"].endswith("/lotto")
    assert db.session.get(LottoPhoto, photo_id).skipped
    response = user_client.post(f"/lotto/{photo_id}", data={"action": "unskip"})
    assert response.headers["Location"].endswith(f"/lotto/{photo_id}")
    assert not db.session.get(LottoPhoto, photo_id).skipped


def test_delete(user_client):
    photo_id = _make_photo("admin")
    other = _make_photo("u2", data=b"x")
    assert user_client.post(f"/lotto/{other}/delete").status_code == 404
    response = user_client.post(f"/lotto/{photo_id}/delete")
    assert response.headers["Location"].endswith("/lotto")
    assert db.session.get(LottoPhoto, photo_id) is None


def test_export_labeled_and_all(user_client):
    done = _make_photo("admin", boxes=[BOX], labeled=True, split="test")
    todo = _make_photo("admin", data=b"todo")
    _make_photo("admin", data=b"skip", skipped=True, labeled=True)
    _make_photo("u2", data=b"other", labeled=True)

    response = user_client.get("/lotto/export.zip")
    assert response.mimetype == "application/zip"
    assert "lotto-labeled-" in response.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        lines = archive.read("manifest.jsonl").decode().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["id"] == done
        assert entry["split"] == "test"
        assert entry["boxes"] == [BOX]
        assert archive.read(entry["file"]) == JPEG
        assert entry["file"] == f"images/{done}.jpg"

    response = user_client.get("/lotto/export.zip?scope=all")
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        ids = {json.loads(line)["id"] for line in archive.read("manifest.jsonl").decode().splitlines()}
    assert ids == {done, todo}


def test_export_empty(user_client):
    response = user_client.get("/lotto/export.zip?scope=bogus")
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.read("manifest.jsonl") == b""


def test_image_ext():
    assert lotto._image_ext(SimpleNamespace(content_type="image/jpeg")) == "jpg"
    assert lotto._image_ext(SimpleNamespace(content_type="image/png")) == "png"


def test_predictions_upload(user_client):
    photo_id = _make_photo("admin", boxes=[])
    other = _make_photo("u2", boxes=[], data=b"x")
    payload = {photo_id: PRED, other: PRED, "missing": PRED}
    response = user_client.post(
        "/lotto/predictions",
        data={"predictions": (io.BytesIO(json.dumps(payload).encode()), "predictions.json")},
        content_type="multipart/form-data",
    )
    assert response.headers["Location"].endswith("/lotto")
    assert json.loads(db.session.get(LottoPhoto, photo_id).boxes_json)[0]["pred"] == "20"
    assert json.loads(db.session.get(LottoPhoto, other).boxes_json) == []


@pytest.mark.parametrize("body", [None, b"\xff\xfe", b"[1, 2]"])
def test_predictions_upload_rejects_bad_files(user_client, body):
    data = {} if body is None else {"predictions": (io.BytesIO(body), "p.json")}
    response = user_client.post("/lotto/predictions", data=data, content_type="multipart/form-data")
    assert response.headers["Location"].endswith("/lotto")


def test_normal_user_cannot_open_lotto(notesync_app, notesync_client):
    _make_user("u2", "bob")
    _login(notesync_app, notesync_client, "u2")
    photo_id = _make_photo("u2")
    for method, url in [
        ("get", "/lotto"),
        ("post", "/lotto/upload"),
        ("get", f"/lotto/{photo_id}"),
        ("get", f"/lotto/{photo_id}/image"),
        ("get", "/lotto/export.zip"),
        ("post", "/lotto/predictions"),
    ]:
        response = getattr(notesync_client, method)(url)
        assert response.status_code == 302, url
        assert "/auth/login-ui" in response.headers["Location"]
    # No Lotto entry in the top navigation for anyone.
    page = notesync_client.get("/lotto/" + photo_id, follow_redirects=True).get_data(as_text=True)
    assert ">Lotto</a>" not in page


def test_routes_redirect_when_user_missing(notesync_app, notesync_client):
    # Admin token, but no user row: still sent to the login page.
    _login(notesync_app, notesync_client, "admin")
    for method, url in [
        ("get", "/lotto"),
        ("post", "/lotto/upload"),
        ("get", "/lotto/x"),
        ("post", "/lotto/x"),
        ("post", "/lotto/x/delete"),
        ("get", "/lotto/x/image"),
        ("get", "/lotto/export.zip"),
        ("post", "/lotto/predictions"),
    ]:
        response = getattr(notesync_client, method)(url)
        assert response.status_code == 302, url
        assert "/auth/login-ui" in response.headers["Location"]


def test_lotto_styles_leave_store_calculator_rows_alone():
    # The Store Accounting calculator's table rows are <tr class="lotto-row">
    # (its JS selects them by that class). A stylesheet rule on .lotto-row
    # (e.g. display: flex) breaks that table, so the lotto pages use
    # .lotto-actions for their button rows instead.
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "src" / "safe_family"
    css = (root / "static" / "css" / "styles.css").read_text()
    assert ".lotto-row" not in css
    calculator = (root / "templates" / "miscellaneous" / "store_calculator.html").read_text()
    assert 'class="lotto-row' in calculator
