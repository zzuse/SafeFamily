"""API routes for notesync and auth exchange."""

import base64
import logging
import time
from datetime import timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from pydantic import ValidationError

from config.settings import settings
from src.safe_family.core.auth import consume_auth_code, require_api_key
from src.safe_family.core.extensions import db
from src.safe_family.core.models import Note, User
from src.safe_family.notesync.schemas import (
    AuthExchangeRequest,
    AuthExchangeResponse,
    NotePayload,
    SyncNoteResult,
    SyncRequest,
    SyncResponse,
    UserInfo,
)
from src.safe_family.notesync.service import apply_sync_ops

api_bp = Blueprint("api", __name__)
logger = logging.getLogger(__name__)


def _note_model_to_payload(note: Note) -> NotePayload:
    return NotePayload(
        id=note.id,
        text=note.text,
        isPinned=note.is_pinned,
        tags=[tag.name for tag in note.tags],
        createdAt=note.created_at,
        updatedAt=note.updated_at,
        deletedAt=note.deleted_at,
    )


def _media_model_to_dict(media) -> dict:
    return {
        "id": media.id,
        "noteId": media.note_id,
        "kind": media.kind,
        "filename": media.filename,
        "contentType": media.content_type,
        "checksum": media.checksum,
        "dataBase64": base64.b64encode(media.data).decode("ascii"),
    }


def _note_to_payload(note, fallback: NotePayload) -> NotePayload:
    if note is None:
        return fallback
    return NotePayload(
        id=note.id,
        text=note.text,
        isPinned=note.is_pinned,
        tags=[tag.name for tag in note.tags],
        createdAt=note.created_at,
        updatedAt=note.updated_at,
        deletedAt=note.deleted_at,
    )


@api_bp.post("/notesync")
@require_api_key
@jwt_required()
def notesync():
    """Apply sync operations for notes."""
    start = time.perf_counter()
    payload_bytes = request.data or b""
    try:
        payload = SyncRequest.model_validate_json(request.data)
    except ValidationError as exc:
        error_payload = {"error": "invalid_request", "details": exc.errors()}
        logger.warning(
            "notesync response status=400 size=%s errors=%s body=%s",
            len(payload_bytes),
            len(exc.errors()),
            error_payload,
        )
        return jsonify(error_payload), 400

    user_id = get_jwt_identity()
    if not user_id:
        error_payload = {"error": "unauthorized"}
        logger.warning("notesync response status=401 body=%s", error_payload)
        return jsonify(error_payload), 401

    try:
        results = apply_sync_ops(payload.ops, user_id=user_id)
    except ValueError as exc:
        db.session.rollback()
        error_payload = {"error": str(exc)}
        logger.warning(
            "notesync response status=400 user=%s body=%s",
            user_id,
            error_payload,
        )
        return jsonify(error_payload), 400

    counts = {"applied": 0, "skipped": 0, "conflict": 0}
    for _, result, _ in results:
        if result in counts:
            counts[result] += 1
        else:
            counts[result] = counts.get(result, 0) + 1
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "notesync completed user=%s ops=%s applied=%s skipped=%s conflict=%s duration_ms=%.2f",
        user_id,
        len(payload.ops),
        counts.get("applied", 0),
        counts.get("skipped", 0),
        counts.get("conflict", 0),
        duration_ms,
    )

    response_results = []
    for note, result, fallback_note in results:
        note_payload = _note_to_payload(note, fallback_note)
        response_results.append(
            SyncNoteResult(
                noteId=note_payload.id,
                result=result,
                note=note_payload,
            ),
        )

    response = SyncResponse(results=response_results)
    response_payload = response.model_dump(mode="json")

    logger.debug(
        "notesync response status=200 body=%s",
        response_payload,
    )
    return jsonify(response_payload)


@api_bp.get("/notes")
@require_api_key
@jwt_required()
def get_notes():
    """Return recent notes for the authenticated user."""
    limit_raw = request.args.get("limit", "10")
    try:
        limit = int(limit_raw)
    except ValueError:
        return jsonify({"error": "invalid_limit"}), 400
    if limit < 1:
        return jsonify({"error": "invalid_limit"}), 400

    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    notes = (
        Note.query.filter(Note.user_id == user_id, Note.deleted_at.is_(None))
        .order_by(Note.updated_at.desc())
        .limit(limit)
        .all()
    )
    response_notes = []
    response_media = []
    for note in notes:
        response_notes.append(_note_model_to_payload(note).model_dump(mode="json"))
        for media in note.media:
            response_media.append(_media_model_to_dict(media))
    return jsonify({"notes": response_notes, "media": response_media})


@api_bp.post("/auth/exchange")
def auth_exchange():
    """Exchange a short-lived auth code for a JWT access token."""
    try:
        payload = AuthExchangeRequest.model_validate_json(request.data)
    except ValidationError as exc:
        return jsonify({"error": "invalid_request", "details": exc.errors()}), 400

    auth_code = consume_auth_code(payload.code)
    if auth_code is None:
        return jsonify({"error": "invalid_code"}), 400

    user = User.query.get(auth_code.user_id)
    if user is None:
        return jsonify({"error": "user_not_found"}), 404

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)
    expires_in = int(
        timedelta(hours=settings.JWT_ACCESS_TOKEN_EXPIRES).total_seconds(),
    )
    response = AuthExchangeResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=UserInfo(id=user.id, username=user.username, email=user.email),
    )
    return jsonify(response.model_dump(mode="json"))
