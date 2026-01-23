"""Notes URL routes for the Safe Family application."""

import io
from datetime import UTC, datetime

from flask import Blueprint, abort, flash, redirect, render_template, send_file
from sqlalchemy.orm import joinedload

from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import local_tz
from src.safe_family.core.models import Media, Note, Tag, User

notes_bp = Blueprint("notes", __name__)


def _attach_local_timestamp(note: Note) -> None:
    updated_at = note.updated_at
    if updated_at is not None:
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        note.updated_local = updated_at.astimezone(local_tz)
    else:
        note.updated_local = None


@notes_bp.get("/notes")
@login_required
def notes_view():
    """Render the notes viewer page."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")
    notes = (
        Note.query.filter(Note.user_id == user.id, Note.deleted_at.is_(None))
        .order_by(Note.created_at.desc())
        .all()
    )
    for note in notes:
        _attach_local_timestamp(note)
    return render_template("notes/notes.html", notes=notes)


@notes_bp.get("/timeline")
@login_required
def timeline():
    """Render the timeline (max 3 public notes per user)."""
    public_notes = (
        Note.query.join(Note.tags)
        .filter(Note.deleted_at.is_(None), Tag.name.ilike("public"))
        .options(joinedload(Note.tags), joinedload(Note.media))
        .order_by(Note.user_id, Note.created_at.desc())
        .all()
    )

    notes_by_user: dict[str, list[Note]] = {}
    for note in public_notes:
        bucket = notes_by_user.setdefault(note.user_id, [])
        if len(bucket) >= 3:
            continue
        _attach_local_timestamp(note)
        bucket.append(note)

    user_ids = list(notes_by_user.keys())
    users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
    user_map = {user.id: user.username for user in users}

    entries = []
    for user_id, notes in notes_by_user.items():
        latest = notes[0].created_at if notes else None
        entries.append(
            {
                "user_id": user_id,
                "username": user_map.get(user_id, user_id),
                "notes": notes,
                "latest": latest,
            },
        )
    entries.sort(
        key=lambda entry: entry["latest"] or datetime.min,
        reverse=True,
    )

    return render_template("notes/timeline.html", entries=entries)


@notes_bp.get("/notes/media/<media_id>")
@login_required
def notes_media(media_id: str):
    """Serve note media blobs for the notes viewer."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")
    media = Media.query.filter_by(id=media_id, user_id=user.id).one_or_none()
    if not media:
        abort(404)
    return send_file(
        io.BytesIO(media.data),
        mimetype=media.content_type,
        download_name=media.filename,
    )
