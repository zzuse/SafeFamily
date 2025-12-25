"""Tests for core models."""

from types import SimpleNamespace

from src.safe_family.core import models


class FakeSession:
    def __init__(self):
        self.added = []
        self.deleted = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.commits += 1


def test_user_password_and_persistence(monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr(models, "db", SimpleNamespace(session=fake_session))

    user = models.User(username="bob", email="b@b.com")
    user.set_password("secret")
    assert user.check_password("secret")

    user.save()
    assert fake_session.added[0] is user
    assert fake_session.commits == 1

    user.change_password("secret", "new")
    assert user.check_password("new")
    assert fake_session.commits >= 2

    user.delete()
    assert fake_session.deleted[0] is user


def test_token_blocklist_save(monkeypatch):
    fake_session = FakeSession()
    monkeypatch.setattr(models, "db", SimpleNamespace(session=fake_session))

    token = models.TokenBlocklist(jti="abc123")
    token.save()

    assert fake_session.added[0] is token
    assert fake_session.commits == 1
