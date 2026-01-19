"""API routes for notesync and auth exchange."""

from datetime import timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from pydantic import ValidationError

from config.settings import settings
from src.safe_family.core.auth import consume_auth_code, require_api_key
from src.safe_family.core.extensions import db
from src.safe_family.core.models import User
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
    try:
        payload = SyncRequest.model_validate_json(request.data)
    except ValidationError as exc:
        return jsonify({"error": "invalid_request", "details": exc.errors()}), 400

    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    try:
        results = apply_sync_ops(payload.ops, user_id=user_id)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400

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
    return jsonify(response.model_dump())


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
    expires_in = int(
        timedelta(hours=settings.JWT_ACCESS_TOKEN_EXPIRES).total_seconds(),
    )
    response = AuthExchangeResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserInfo(id=user.id, username=user.username, email=user.email),
    )
    return jsonify(response.model_dump())
