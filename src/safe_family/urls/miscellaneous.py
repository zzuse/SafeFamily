"""Miscellaneous URL routes for the Safe Family application."""

import io
from datetime import UTC

from flask import Blueprint, abort, flash, redirect, render_template, send_file

from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import local_tz
from src.safe_family.core.models import Media, Note

root_bp = Blueprint("index", __name__)


@root_bp.route("/")
def index():
    """Redirect to the suspicious URLs view.

    This route redirects users to the main page for viewing suspicious URLs.
    """
    return redirect("/todo")


@root_bp.route("/store_sum")
@login_required
def store_sum():
    """Redirect to the store_sum page.

    This route redirects users to the store_sum page.
    """
    return render_template("miscellaneous/store_sum.html")


@root_bp.route("/ninja")
@login_required
def ninja_nightmare():
    """Redirect to the store_sum page.

    This route redirects users to the store_sum page.
    """
    return render_template("miscellaneous/ninja_nightmare.html")


@root_bp.get("/notes")
@login_required
def notes_view():
    """Render the notes viewer page."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")
    notes = (
        Note.query.filter(Note.user_id == user.id, Note.deleted_at.is_(None))
        .order_by(Note.updated_at.desc())
        .all()
    )
    for note in notes:
        updated_at = note.updated_at
        if updated_at is not None:
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=UTC)
            note.updated_local = updated_at.astimezone(local_tz)
        else:
            note.updated_local = None
    return render_template("notes/notes.html", notes=notes)


@root_bp.get("/notes/media/<media_id>")
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
