# Notesync Backend Implementation Plan

Goal: Implement a notebook syncing backend for short notes with images, audio clips, and tags. Add `POST /api/notesync` (API key + user JWT) with last-write-wins conflict handling and `POST /api/auth/exchange` for OAuth auth code exchange.

Architecture: A single Flask app with SQLAlchemy models for notes, tags, media, and sync metadata. The `/api/notesync` endpoint authenticates via API key and JWT, scopes data by user id, applies operations transactionally with LWW semantics, stores media blobs in PostgreSQL, and returns authoritative note states. The `/api/auth/exchange` endpoint exchanges short-lived OAuth codes for JWTs.

Tech Stack:
- Python 3.11, Flask, Flask-SQLAlchemy, Flask-JWT-Extended, psycopg2
- pydantic for validation (replace current marshmallow usage)
- pytest

Integration Points:
- App factory: `src/safe_family/app.py`
- Auth, JWT, and auth codes: `src/safe_family/core/auth.py`
- Settings: `config/settings.py`
- Models: `src/safe_family/core/models.py`
- Database extension: `src/safe_family/core/extensions.py`

---

### Login URL and Callback Contract (Custom URL Scheme)

The iOS app opens the login URL in an external browser. This URL must start the OAuth flow and redirect to the provider.

Recommended behavior:
1) `GET /auth/login/google` or `GET /auth/login/github` generates the provider authorization request.
2) Backend redirects to the provider authorize URL.
3) Provider redirects back to your backend callback route with `code`.
4) Backend creates a short-lived notesync auth code.
5) Backend redirects to the app callback URL:
   `zzuse.timeline://auth/callback?code=<notesync-auth-code>`

Expected return:
- A redirect chain that ends at the app callback URL above.
- The app receives the callback and calls `POST /api/auth/exchange`.
- Backend responds with:
  `{ "access_token": "<jwt>", "refresh_token": "<jwt>", "token_type": "Bearer", "expires_in": 10800 }`.

Notes:
- The login URL can be any backend route as long as it ends with the app callback redirect.
- Keep the scheme/host/path aligned with your iOS configuration.

---

### Data Model (reference sketch)

Adapt to Flask-SQLAlchemy (`db.Model`, `db.Table`) and add indexes as needed.

```python
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, LargeBinary, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from backend.db import Base

note_tags = Table(
    "note_tags",
    Base.metadata,
    Column("note_id", String, ForeignKey("notes.id"), primary_key=True),
    Column("tag_id", String, ForeignKey("tags.id"), primary_key=True),
)

class Note(Base):
    __tablename__ = "notes"
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    text = Column(Text, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    tags = relationship("Tag", secondary=note_tags, back_populates="notes")
    media = relationship("Media", back_populates="note")

class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    notes = relationship("Note", secondary=note_tags, back_populates="tags")

class Media(Base):
    __tablename__ = "media"
    id = Column(String, primary_key=True)
    note_id = Column(String, ForeignKey("notes.id"), nullable=False)
    user_id = Column(String, nullable=False, index=True)
    kind = Column(String, nullable=False)  # "image" or "audio"
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    checksum = Column(String, nullable=False)
    data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    note = relationship("Note", back_populates="media")
```

Additional tables for sync metadata:
- `note_sync_ops`: `id`, `user_id`, `op_id`, `note_id`, `applied_at`, `result`
- `auth_codes`: `code_hash`, `user_id`, `expires_at`, `used_at`, `created_at`

---

### Task 1: Settings and configuration

Files:
- Modify `config/settings.py`
- Modify `src/safe_family/app.py`

Steps:
1) Add `NOTESYNC_API_KEY` to settings.
2) Add `NOTESYNC_AUTH_CODE_TTL_SECONDS` (default: 300).
3) Add `NOTESYNC_MAX_REQUEST_BYTES` for payload size limits.
4) Add `NOTESYNC_CALLBACK_URL` (default: `zzuse.timeline://auth/callback`).
5) Set `MAX_CONTENT_LENGTH` in Flask config to prevent oversized uploads.

---

### Task 2: Notesync models

Files:
- Modify `src/safe_family/core/models.py`

Steps:
1) Implement `Note`, `Tag`, `Media`, and `note_tags` using Flask-SQLAlchemy.
2) Implement `NoteSyncOp` for idempotency (unique on `user_id` + `op_id`).
3) Implement `AuthCode` with hashed codes and expiry checks.
4) Add indexes on `user_id`, `updated_at`, and `note_id`.

---

### Task 3: Database migrations or schema script

Files:
- Add `scripts/notesync_schema.sql` (or extend `scripts/migrate.py`)

Steps:
1) Create SQL DDL for tables and indexes.
2) Document how to apply in staging/production.
3) Ensure constraints for tag uniqueness and sync op idempotency.

---

### Task 4: Request/response schemas (pydantic)

Files:
- Create `src/safe_family/notesync/schemas.py`
- Modify `src/safe_family/core/schemas.py`
- Modify `src/safe_family/users/users.py`

Schema requirements:
- `SyncRequest` with `ops[]`
- `Operation` with `opId`, `opType`, `note`, `media[]`
- `NotePayload`: `id`, `text`, `isPinned`, `tags[]`, `createdAt`, `updatedAt`, `deletedAt`
- `MediaPayload`: `id`, `noteId`, `kind`, `filename`, `contentType`, `checksum`, `dataBase64`

Steps:
1) Define pydantic models for notesync payloads and responses.
2) Validate ISO timestamps and required fields.
3) Enforce `kind` in {"image", "audio"}.
4) Validate `dataBase64` presence for media.
5) Replace existing marshmallow `UserSchema` with pydantic `UserOut`.
6) Update user listing to serialize via pydantic (`model_dump()` or `TypeAdapter`).
7) Update tests that assert marshmallow behavior to use pydantic serialization.

---

### Task 5: Auth helpers (API key + JWT)

Files:
- Modify `src/safe_family/core/auth.py`

Steps:
1) Implement `require_api_key()` in `core/auth.py` to validate `X-API-Key`.
2) Use `@jwt_required()` and `get_jwt_identity()` for user auth.
3) Reject missing/invalid auth with 401.

---

### Task 6: Notesync LWW service

Files:
- Create `src/safe_family/notesync/service.py`

Steps:
1) Wrap sync application in a DB transaction.
2) For each op:
   - Skip if `note_sync_ops` already has `op_id` for user.
   - Load existing note by `id` and `user_id`.
   - Compare `updatedAt` with `updated_at`.
   - If `opType == "delete"`, set `deleted_at` if newer.
   - If incoming is newer, upsert note fields.
3) Tags:
   - Replace note tags with payload tags on accepted updates.
   - Create missing tags per user.
4) Media:
   - Deduplicate per note by `checksum` (SHA-256 hex). If the note already has a
     media item with the same checksum, ignore the new media payload.
   - Decode `dataBase64` and upsert by `id` when needed; skip re-decoding if the
     checksum is unchanged.
   - Decide whether to delete media not present in payload (document the rule).
5) Return authoritative note state and result per op: "applied", "skipped", "conflict".

---

### Task 7: Notesync endpoint (blueprint prefix: /api)

Files:
- Modify `src/safe_family/api/routes.py` to add `POST /notesync`
- Modify `src/safe_family/app.py` to register the API blueprint with `url_prefix="/api"`

Endpoint:
- `POST /api/notesync`

Steps:
1) Require API key + JWT.
2) Validate request schema.
3) Call sync service and return results list.

Example:
```bash
curl -X POST https://zzuse.duckdns.org/api/notesync \
  -H "X-API-Key: <your-api-key>" \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "ops": [{
      "opId": "op-1",
      "opType": "upsert",
      "note": {
        "id": "note-1",
        "text": "Hello",
        "isPinned": false,
        "tags": [],
        "createdAt": "2025-01-01T12:00:00Z",
        "updatedAt": "2025-01-01T12:00:00Z",
        "deletedAt": null
      },
      "media": []
    }]
  }'
```

---

### Task 7b: Notes list endpoint

Endpoint:
- `GET /api/notes?limit=10`

Behavior:
- Requires API key + JWT.
- Returns the most recently updated notes first (non-deleted only).
- Response includes a top-level `media` array (may be empty).
- Datetimes are returned in ISO-8601 with a `Z` suffix (UTC).

Response shape:
```json
{
  "notes": [
    {
      "id": "note-1",
      "text": "Hello",
      "isPinned": false,
      "tags": [],
      "createdAt": "2025-01-01T12:00:00Z",
      "updatedAt": "2025-01-01T12:00:00Z",
      "deletedAt": null
    }
  ],
  "media": [
    {
      "id": "media-1",
      "noteId": "note-1",
      "kind": "image",
      "filename": "photo.jpg",
      "contentType": "image/jpeg",
      "checksum": "sha256hex...",
      "dataBase64": "..."
    }
  ]
}
```

---

### Task 8: Auth code exchange endpoint (API routes)

Files:
- Modify `src/safe_family/api/routes.py` to add `POST /auth/exchange`

Endpoint:
- `POST /api/auth/exchange` with `{ "code": "..." }`

Steps:
1) Hash and look up code in `auth_codes`.
2) Validate expiry and used state.
3) Mark code as used and issue JWT access + refresh tokens.
4) Return `access_token`, `refresh_token`, `token_type`, `expires_in`, and `user`.

---

### Task 9: OAuth callback integration (auth code issuance)

Files:
- Modify `src/safe_family/core/auth.py`

Steps:
1) On GitHub/Google login success, generate a short-lived auth code for the user.
2) Store only a hash in `auth_codes` with expiry and used state.
3) Redirect to the custom scheme: `zzuse.timeline://auth/callback?code=...`.
4) Keep a fallback HTML page at `/auth/callback` for when the app is not installed.

Auth code usage (aligned with your flow):
- OAuth callback in `core/auth.py` creates the code after user identity is confirmed.
- Server redirects to `zzuse.timeline://auth/callback?code=...` (custom URL scheme).
- iOS handles the URL and calls `POST /api/auth/exchange`.
- Exchange validates and marks the code as used, then issues an access token.

---

### Task 10: Tests

Files:
- Add `tests/test_notesync_models.py`
- Add `tests/test_notesync_schemas.py`
- Add `tests/test_notesync_auth.py`
- Add `tests/test_notesync_lww.py`
- Add `tests/test_notesync_endpoint.py`
- Add `tests/test_auth_exchange.py`

Coverage goals:
- LWW skip of older updates
- Delete tombstone handling
- Tag creation and note-tag join handling
- Media upsert and validation
- API key + JWT enforcement
- Auth code exchange success and failures

---

### Task 11: API contract docs

Files:
- Update `docs/api.md`

Include:
- `/api/notesync` request/response examples
- `/api/auth/exchange` request/response examples
- Error codes and response shapes
- LWW semantics and tombstone behavior

---

### Task 12: Operational safeguards

Steps:
1) Enforce request size limits and media size bounds.
2) Validate `content_type` against allowed media types.
3) Add checksum verification (optional).
4) Add metrics/logging around sync timing and failures.

---

### Task 13: Notes viewer UI (web page)

Goal:
- Provide a web page to browse notes stored in the notesync tables.
- Show note text, tags, images, and audio clips.
- Sort notes with the most recently updated first.

Files:
- Modify `src/safe_family/urls/miscellaneous.py` (web routes)
- Add `src/safe_family/templates/notes/notes.html`

Routes:
- `GET /notes`: list notes (requires session login)
- `GET /notes/media/<media_id>`: stream image/audio for a note (requires session login)

Steps:
1) Query notes by `user_id` with `deleted_at is null`, ordered by `updated_at desc`.
2) Render notes in a template using existing site layout.
3) For each media record, render:
   - `<img>` for image content types
   - `<audio controls>` for audio content types
4) Serve media blobs from the database using `send_file` and the stored `content_type`.

Notes:
- Use the session-based `login_required` to protect the page.
- Scope all note/media queries by the current user id.

---

## Verification

- `pytest tests/test_notesync_models.py`
- `pytest tests/test_notesync_schemas.py`
- `pytest tests/test_notesync_auth.py`
- `pytest tests/test_notesync_lww.py`
- `pytest tests/test_notesync_endpoint.py`
- `pytest tests/test_auth_exchange.py`
