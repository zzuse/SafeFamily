"""Core models for Safe Family application."""

import uuid
from datetime import UTC, datetime

from werkzeug.security import check_password_hash, generate_password_hash

from src.safe_family.core.extensions import db, local_tz


class User(db.Model):
    """User model for Safe Family application."""

    __tablename__ = "users"

    id = db.Column(db.String(), primary_key=True, default=(uuid.uuid4))
    username = db.Column(db.String(), nullable=False)
    email = db.Column(db.String(), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    # Relationship to goals
    goals = db.relationship(
        "LongTermGoal",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """Return a string representation of the User."""
        return f"<User(username='{self.username}', Role: '{self.role}', email='{self.email}')>"

    def get_id(self):
        """Return the user ID."""
        return self.id

    def set_password(self, password: str):
        """Set the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str):
        """Check if the provided password matches the stored password hash."""
        return check_password_hash(self.password_hash, password)

    def change_password(self, old_password: str, new_password: str):
        """Change the user's password."""
        if self.check_password(old_password):
            self.password_hash = generate_password_hash(new_password)
            self.save()
            return True
        return False

    @classmethod
    def get_user_by_username(cls, username: str):
        """Get a user by their username."""
        return cls.query.filter_by(username=username).first()

    def save(self):
        """Save the user to the database."""
        db.session.add(self)
        db.session.commit()

    def delete(self):
        """Delete the user from the database."""
        db.session.delete(self)
        db.session.commit()


class TokenBlocklist(db.Model):
    """Model for storing revoked JWT tokens."""

    __tablename__ = "token_blocklist"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self) -> str:
        """Return a string representation of the TokenBlocklist."""
        return f"<TokenBlocklist(jti='{self.jti}')>"

    def save(self):
        """Save the token blocklist entry to the database."""
        db.session.add(self)
        db.session.commit()


class LongTermGoal(db.Model):
    """ORM of LONG_TERM_GOALS."""

    __tablename__ = "long_term_goals"

    goal_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.String,
        db.ForeignKey("users.id", onupdate="NO ACTION", ondelete="CASCADE"),
        nullable=False,
    )
    task_text = db.Column(db.Text, nullable=False)
    priority = db.Column(db.Integer, default=3)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    completed_at = db.Column(db.DateTime, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    time_spent = db.Column(db.Integer, default=0)
    is_tracking = db.Column(db.Boolean, default=False)
    tracking_start = db.Column(db.DateTime, nullable=True)

    # Relationship to user
    user = db.relationship("User", back_populates="goals")

    def __repr__(self) -> str:
        """Show String View."""
        return f"<LongTermGoal(goal_id={self.goal_id}, user_id={self.user_id}, task_text={self.task_text}, completed={self.completed})>"

    def get_goal(self, goal_id: int):
        """Retrieve a goal by ID."""
        return (
            db.session.query(LongTermGoal)
            .filter(LongTermGoal.goal_id == goal_id)
            .first()
        )

    def stop_tracking(self):
        """Stop time tracking and update time_spent."""
        if self.is_tracking and self.tracking_start:
            self.time_spent += (
                datetime.now(local_tz) - local_tz.localize(self.tracking_start)
            ).seconds
            self.is_tracking = False
            self.tracking_start = None
            db.session.commit()
        return self

    def add_time_spent(self, goal_id: int, minutes: int):
        """Add time spent on a goal."""
        goal = self.get_goal(goal_id)
        if goal:
            goal.time_spent += minutes * 60
            db.session.commit()
        return goal

    def delete_goal(self):
        """Delete goal."""
        db.session.delete(self)
        db.session.commit()


note_tags = db.Table(
    "note_tags",
    db.Column("note_id", db.String(), db.ForeignKey("notes.id"), primary_key=True),
    db.Column("tag_id", db.String(), db.ForeignKey("tags.id"), primary_key=True),
)


class Note(db.Model):
    """Notesync note model."""

    __tablename__ = "notes"

    id = db.Column(db.String(), primary_key=True)
    user_id = db.Column(db.String(), nullable=False, index=True)
    text = db.Column(db.Text(), nullable=False)
    is_pinned = db.Column(db.Boolean(), default=False, nullable=False)
    created_at = db.Column(db.DateTime(), nullable=False)
    updated_at = db.Column(db.DateTime(), nullable=False, index=True)
    deleted_at = db.Column(db.DateTime(), nullable=True)
    tags = db.relationship("Tag", secondary=note_tags, back_populates="notes")
    media = db.relationship("Media", back_populates="note")


class Tag(db.Model):
    """Notesync tag model."""

    __tablename__ = "tags"
    __table_args__ = (db.UniqueConstraint("user_id", "name", name="uq_tags_user_name"),)

    id = db.Column(db.String(), primary_key=True)
    user_id = db.Column(db.String(), nullable=False, index=True)
    name = db.Column(db.String(), nullable=False)
    notes = db.relationship("Note", secondary=note_tags, back_populates="tags")


class Media(db.Model):
    """Notesync media model."""

    __tablename__ = "media"

    id = db.Column(db.String(), primary_key=True)
    note_id = db.Column(db.String(), db.ForeignKey("notes.id"), nullable=False, index=True)
    user_id = db.Column(db.String(), nullable=False, index=True)
    kind = db.Column(db.String(), nullable=False)
    filename = db.Column(db.String(), nullable=False)
    content_type = db.Column(db.String(), nullable=False)
    checksum = db.Column(db.String(), nullable=False)
    data = db.Column(db.LargeBinary(), nullable=False)
    created_at = db.Column(db.DateTime(), nullable=False, default=lambda: datetime.now(UTC))
    note = db.relationship("Note", back_populates="media")


class NoteSyncOp(db.Model):
    """Idempotency record for notesync operations."""

    __tablename__ = "note_sync_ops"
    __table_args__ = (
        db.UniqueConstraint("user_id", "op_id", name="uq_notesync_user_op"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(), nullable=False, index=True)
    op_id = db.Column(db.String(), nullable=False)
    note_id = db.Column(db.String(), nullable=False, index=True)
    result = db.Column(db.String(), nullable=False)
    applied_at = db.Column(db.DateTime(), nullable=False, default=lambda: datetime.now(UTC))


class AuthCode(db.Model):
    """Short-lived auth code for mobile token exchange."""

    __tablename__ = "auth_codes"

    id = db.Column(db.Integer, primary_key=True)
    code_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    user_id = db.Column(db.String(), nullable=False, index=True)
    created_at = db.Column(db.DateTime(), nullable=False, default=lambda: datetime.now(UTC))
    expires_at = db.Column(db.DateTime(), nullable=False)
    used_at = db.Column(db.DateTime(), nullable=True)

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return True when the auth code is expired."""
        now = now or datetime.now(UTC)
        if self.expires_at.tzinfo is None:
            now = now.replace(tzinfo=None)
        return self.expires_at <= now
