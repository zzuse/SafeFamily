"""Notes URL routes for the Safe Family application."""

import hashlib
import io
import uuid
from datetime import UTC, datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from sqlalchemy.orm import selectinload

from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import db, local_tz
from src.safe_family.core.models import Media, Note, Tag

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

    page = request.args.get("page", 1, type=int)
    per_page = 5

    pagination = (
        Note.query.filter(Note.user_id == user.id, Note.deleted_at.is_(None))
        .options(selectinload(Note.tags), selectinload(Note.media))
        .order_by(Note.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    notes = pagination.items
    for note in notes:
        _attach_local_timestamp(note)

    return render_template(
        "notes/notes.html",
        notes=notes,
        pagination=pagination,
        endpoint="notes.notes_view",
    )


@notes_bp.post("/notes/upload")
@login_required
def upload_note():
    """Create a note (text and/or media files) from the web notes page."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")

    text = (request.form.get("text") or "").strip()
    files = [f for f in request.files.getlist("media") if f and f.filename]
    if not text and not files:
        flash("Nothing to upload: add some text or choose a file.", "warning")
        return redirect(url_for("notes.notes_view"))

    now = datetime.now(UTC).replace(tzinfo=None)
    note = Note(
        id=uuid.uuid4().hex,
        user_id=user.id,
        text=text,
        is_pinned=False,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    db.session.add(note)

    tag_names = {
        name.strip().lower()
        for name in (request.form.get("tags") or "").split(",")
        if name.strip()
    }
    for name in sorted(tag_names):
        tag = Tag.query.filter_by(user_id=user.id, name=name).first()
        if tag is None:
            tag = Tag(id=uuid.uuid4().hex, user_id=user.id, name=name)
            db.session.add(tag)
        note.tags.append(tag)

    for upload in files:
        data = upload.read()
        if not data:
            continue
        content_type = upload.content_type or "application/octet-stream"
        if content_type.startswith("image/"):
            kind = "image"
        elif content_type.startswith("audio/"):
            kind = "audio"
        else:
            kind = "file"
        media = Media(
            id=uuid.uuid4().hex,
            note_id=note.id,
            user_id=user.id,
            kind=kind,
            filename=upload.filename,
            content_type=content_type,
            checksum=f"sha256:{hashlib.sha256(data).hexdigest()}",
            data=data,
            created_at=now,
        )
        db.session.add(media)

    db.session.commit()
    flash("Note uploaded successfully.", "success")
    return redirect(url_for("notes.notes_view"))


@notes_bp.post("/notes/delete/<note_id>")
@login_required
def delete_note(note_id: str):
    """Delete a note and its associated media."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")

    note = Note.query.filter_by(id=note_id, user_id=user.id).one_or_none()
    if not note:
        abort(404)

    db.session.delete(note)
    db.session.commit()
    flash("Note deleted successfully.", "success")
    return redirect(url_for("notes.notes_view"))


@notes_bp.get("/notes/media/<media_id>")
@login_required
def notes_media(media_id: str):
    """Serve note media blobs for the notes viewer."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")
    media = (
        Media.query.options(selectinload(Media.note).selectinload(Note.tags))
        .filter_by(id=media_id)
        .one_or_none()
    )
    if not media:
        abort(404)
    if media.user_id != user.id:
        note = media.note
        is_public = (
            note is not None
            and note.deleted_at is None
            and any(tag.name.lower() == "public" for tag in note.tags)
        )
        if not is_public:
            abort(404)

    mimetype = media.content_type
    if media.filename.lower().endswith(".m4a"):
        mimetype = "audio/mp4"

    return send_file(
        io.BytesIO(media.data),
        mimetype=mimetype,
        download_name=media.filename,
    )
