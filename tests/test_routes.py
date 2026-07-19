"""Route and CLI tests using shared fixtures."""


def test_root_redirects_to_todo(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/todo")


def test_store_sum_renders_when_logged_in(client, monkeypatch):
    # Bypass JWT validation and provide a session token
    monkeypatch.setattr(
        "src.safe_family.core.auth.decode_token",
        lambda token: {"sub": "user"},
    )
    with client.session_transaction() as sess:
        sess["access_token"] = "token"

    resp = client.get("/store_sum")
    assert resp.status_code == 200


def test_calc_guide_renders_when_logged_in(client, monkeypatch):
    # Bypass JWT validation and provide a session token
    monkeypatch.setattr(
        "src.safe_family.core.auth.decode_token",
        lambda token: {"sub": "user"},
    )
    with client.session_transaction() as sess:
        sess["access_token"] = "token"

    resp = client.get("/calc_guide")
    assert resp.status_code == 200
    assert b"Yaw Calculator" in resp.data
    assert b"Store Accounting Tool" in resp.data


def test_yaw_calc_renders_when_logged_in(client, monkeypatch):
    # Bypass JWT validation and provide a session token
    monkeypatch.setattr(
        "src.safe_family.core.auth.decode_token",
        lambda token: {"sub": "user"},
    )
    with client.session_transaction() as sess:
        sess["access_token"] = "token"

    resp = client.get("/yaw_calc")
    assert resp.status_code == 200
    assert b"atan2" in resp.data


def _countdown_login(notesync_client, monkeypatch, user_id="user-1"):
    from src.safe_family.core.extensions import db
    from src.safe_family.core.models import User

    user = User(id=user_id, username="alice", email="a@example.com")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()

    monkeypatch.setattr(
        "src.safe_family.core.auth.decode_token",
        lambda token: {"sub": user_id},
    )
    with notesync_client.session_transaction() as sess:
        sess["access_token"] = "token"
    return user


def test_countdown_falls_back_to_env_defaults(notesync_client, monkeypatch):
    _countdown_login(notesync_client, monkeypatch)
    monkeypatch.setattr(
        "src.safe_family.urls.miscellaneous.settings.COUNTDOWN_DATE",
        "2026-12-31",
    )
    monkeypatch.setattr(
        "src.safe_family.urls.miscellaneous.settings.COUNTDOWN_DESCRIPTION",
        "New Year Eve",
    )

    resp = notesync_client.get("/countdown")
    assert resp.status_code == 200
    assert b"2026-12-31" in resp.data
    assert b"New Year Eve" in resp.data


def test_countdown_save_and_render_per_user(notesync_client, monkeypatch):
    _countdown_login(notesync_client, monkeypatch)

    resp = notesync_client.post(
        "/countdown",
        data={"target_date": "2027-03-15", "description": "Trip to Japan"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"2027-03-15" in resp.data
    assert b"Trip to Japan" in resp.data

    # Saving again updates the same row instead of adding a new one
    resp = notesync_client.post(
        "/countdown",
        data={"target_date": "2027-04-01", "description": "Moved trip"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"2027-04-01" in resp.data

    from src.safe_family.core.models import CountdownConfig

    assert CountdownConfig.query.count() == 1


def test_countdown_save_rejects_bad_date(notesync_client, monkeypatch):
    _countdown_login(notesync_client, monkeypatch)

    resp = notesync_client.post(
        "/countdown",
        data={"target_date": "not-a-date", "description": "x"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Invalid date" in resp.data

    from src.safe_family.core.models import CountdownConfig

    assert CountdownConfig.query.count() == 0


def test_store_sum_static_renders_when_logged_in(client, monkeypatch):
    # Bypass JWT validation and provide a session token
    monkeypatch.setattr(
        "src.safe_family.core.auth.decode_token",
        lambda token: {"sub": "user"},
    )
    with client.session_transaction() as sess:
        sess["access_token"] = "token"

    resp = client.get("/store_sum_static")
    assert resp.status_code == 200

