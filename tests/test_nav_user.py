"""Tests for the top bar: the logged-in user's avatar, name, badge and Logout."""

import re

from flask_jwt_extended import create_access_token
from sqlalchemy.exc import OperationalError

from src.safe_family.core.extensions import db
from src.safe_family.core.models import User


def _user(user_id, username):
    user = User(id=user_id, username=username, email=f"{username}@example.com", role="user")
    user.set_password("secret")
    db.session.add(user)
    db.session.commit()


def _login(app, client, user_id, **claims):
    with app.app_context():
        token = create_access_token(identity=user_id, additional_claims=claims or None)
    with client.session_transaction() as sess:
        sess["access_token"] = token


def _topbar(client):
    html = client.get("/calc_guide").get_data(as_text=True)
    return html.split('<header class="sf-topbar">', 1)[1].split("</header>", 1)[0]


def _avatar(topbar):
    return re.search(r'<div class="sf-avatar[^"]*"[^>]*>([^<]*)</div>', topbar).group(1).strip()


def test_avatar_shows_each_users_own_initial(notesync_app, notesync_client):
    _user("u-a", "alice")
    _user("u-b", "bob")
    _login(notesync_app, notesync_client, "u-a")
    topbar = _topbar(notesync_client)
    assert _avatar(topbar) == "A"
    assert '<span class="sf-user-name">alice</span>' in topbar
    assert "GAME MASTER" not in topbar

    _login(notesync_app, notesync_client, "u-b")
    assert _avatar(_topbar(notesync_client)) == "B"


def test_logout_sits_by_the_avatar_not_in_the_menu(notesync_app, notesync_client):
    _user("u-a", "alice")
    _login(notesync_app, notesync_client, "u-a")
    topbar = _topbar(notesync_client)
    nav = topbar.split('<nav class="sf-nav">', 1)[1].split("</nav>", 1)[0]
    user_area = topbar.split('<div class="sf-user">', 1)[1]
    assert "Logout" not in nav
    assert 'class="sf-user-logout"' in user_area


def test_admin_gets_badge_and_ring(notesync_app, notesync_client, monkeypatch):
    monkeypatch.setattr("config.settings.settings.ADMIN_IDENTITY", "u-admin")
    _user("u-admin", "zzuse")
    _login(notesync_app, notesync_client, "u-admin", is_admin="admin")
    topbar = _topbar(notesync_client)
    assert "GAME MASTER" in topbar
    assert 'class="sf-avatar is-admin"' in topbar
    assert _avatar(topbar) == "Z"


def test_admin_claim_for_another_identity_is_not_trusted(notesync_app, notesync_client, monkeypatch):
    monkeypatch.setattr("config.settings.settings.ADMIN_IDENTITY", "u-admin")
    _user("u-a", "alice")
    _login(notesync_app, notesync_client, "u-a", is_admin="admin")
    assert "GAME MASTER" not in _topbar(notesync_client)


def test_token_for_missing_user_shows_placeholder(notesync_app, notesync_client):
    _login(notesync_app, notesync_client, "no-such-user")
    topbar = _topbar(notesync_client)
    assert _avatar(topbar) == "?"
    assert "sf-user-name" not in topbar


def test_database_error_still_renders_the_page(notesync_app, notesync_client, monkeypatch):
    _user("u-a", "alice")
    _login(notesync_app, notesync_client, "u-a")

    def broken():
        msg = "select"
        raise OperationalError(msg, {}, Exception("db down"))

    monkeypatch.setattr("src.safe_family.app.get_current_username", broken)
    resp = notesync_client.get("/calc_guide")
    assert resp.status_code == 200
    assert _avatar(resp.get_data(as_text=True).split('<header class="sf-topbar">', 1)[1]) == "?"


def test_logged_out_shows_login_links_and_no_avatar(notesync_client):
    html = notesync_client.get("/auth/login-ui").get_data(as_text=True)
    topbar = html.split('<header class="sf-topbar">', 1)[1].split("</header>", 1)[0]
    assert "Login" in topbar
    assert "Register" in topbar
    assert "sf-avatar" not in topbar
