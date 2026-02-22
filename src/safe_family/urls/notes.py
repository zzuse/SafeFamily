"""Notes URL routes for the Safe Family application."""

import io
from datetime import UTC, datetime

from flask import Blueprint, abort, flash, redirect, render_template, send_file, request, url_for
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import db, local_tz
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
    
    page = request.args.get('page', 1, type=int)
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
        endpoint='notes.notes_view'
    )


@notes_bp.get("/timeline")
@login_required
def timeline():
    """Render the timeline (max 3 public notes per user)."""
    page = request.args.get('page', 1, type=int)
    per_page = 5

    # Base query for public notes
    base_query = Note.query.filter(
        Note.deleted_at.is_(None),
        Note.tags.any(Tag.name.ilike("public")),
    )

    # Note: The original timeline logic fetched 3 notes per user. 
    # To properly paginate, we should probably paginate by users who have public notes,
    # then fetch notes for those users.
    
    # Get distinct user_ids with public notes
    user_ids_query = (
        db.session.query(Note.user_id)
        .filter(Note.deleted_at.is_(None), Note.tags.any(Tag.name.ilike("public")))
        .distinct()
    )
    
    pagination = user_ids_query.paginate(page=page, per_page=per_page, error_out=False)
    target_user_ids = [r[0] for r in pagination.items]

    if not target_user_ids:
        return render_template("notes/timeline.html", entries=[], pagination=pagination, endpoint='notes.timeline')

    note_rankings = (
        Note.query.with_entities(
            Note.id.label("note_id"),
            Note.user_id.label("user_id"),
            Note.created_at.label("created_at"),
            func.row_number()
            .over(partition_by=Note.user_id, order_by=Note.created_at.desc())
            .label("rn"),
        )
        .filter(
            Note.deleted_at.is_(None),
            Note.tags.any(Tag.name.ilike("public")),
            Note.user_id.in_(target_user_ids)
        )
        .subquery()
    )

    public_notes = (
        Note.query.join(note_rankings, Note.id == note_rankings.c.note_id)
        .filter(note_rankings.c.rn <= 3)
        .options(
            selectinload(Note.tags),
            selectinload(Note.media).load_only(
                Media.id,
                Media.note_id,
                Media.user_id,
                Media.kind,
                Media.filename,
                Media.content_type,
                Media.checksum,
                Media.created_at,
            ),
        )
        .order_by(note_rankings.c.user_id, note_rankings.c.created_at.desc())
        .all()
    )

    notes_by_user: dict[str, list[Note]] = {}
    for note in public_notes:
        bucket = notes_by_user.setdefault(note.user_id, [])
        _attach_local_timestamp(note)
        bucket.append(note)

    users = User.query.filter(User.id.in_(target_user_ids)).all()
    user_map = {user.id: user.username for user in users}

    entries = []
    for user_id in target_user_ids:
        notes = notes_by_user.get(user_id, [])
        latest = notes[0].created_at if notes else None
        entries.append(
            {
                "user_id": user_id,
                "username": user_map.get(user_id, user_id),
                "notes": notes,
                "latest": latest,
            },
        )
    
    # Sort entries by the latest note within the set of users we fetched
    entries.sort(
        key=lambda entry: entry["latest"] or datetime.min,
        reverse=True,
    )

    user = get_current_username()
    current_user_id = user.id if user else None

    return render_template(
        "notes/timeline.html", 
        entries=entries, 
        current_user_id=current_user_id, 
        pagination=pagination,
        endpoint='notes.timeline'
    )


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


@notes_bp.post("/notes/unpublish/<note_id>")
@login_required
def unpublish_note(note_id: str):
    """Remove the 'public' tag from a note so it no longer appears on the timeline."""
    user = get_current_username()
    if not user:
        flash("Please log in first.", "warning")
        return redirect("/auth/login-ui")

    note = Note.query.filter_by(id=note_id, user_id=user.id).one_or_none()
    if not note:
        abort(404)

    # Remove the 'public' tag
    public_tags = [t for t in note.tags if t.name.lower() == "public"]
    for t in public_tags:
        note.tags.remove(t)

    db.session.commit()
    flash("Note removed from public timeline.", "success")
    return redirect(url_for("notes.timeline"))


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
