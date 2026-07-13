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

