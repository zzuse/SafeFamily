"""Tests for core models."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from src.safe_family.core import models
from src.safe_family.core.extensions import db, local_tz
from src.safe_family.core.models import LongTermGoal, User


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


def test_long_term_goal_tracking(notesync_app):
    with notesync_app.app_context():
        user = User(id="u-goal", username="alice", email="a@example.com")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

        started = datetime.now(local_tz) - timedelta(minutes=10)
        goal = LongTermGoal(
            user_id=user.id,
            task_text="Learn",
            priority=1,
            is_tracking=True,
            tracking_start=started.replace(tzinfo=None),
        )
        db.session.add(goal)
        db.session.commit()

        updated = goal.stop_tracking()
        assert updated.is_tracking is False
        assert updated.time_spent > 0

        updated.add_time_spent(updated.goal_id, 5)
        assert updated.time_spent >= 5 * 60

        updated.delete_goal()
        assert LongTermGoal.query.get(updated.goal_id) is None
