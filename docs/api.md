# API

## Auth headers

Notesync endpoints require both:
- `X-API-Key: <api-key>`
- `Authorization: Bearer <access-token>`

---

## GET /api/notes

Return recent notes for the authenticated user.

Query:
- `limit` (optional, default `10`)

Response:
- `notes`: array of note objects (newest first)
- `media`: array of media objects (may be empty)
- Datetimes are ISO-8601 UTC with a `Z` suffix.

Example response:
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

Errors:
- `400 { "error": "invalid_limit" }`
- `401 { "error": "unauthorized" }`

---

## POST /api/notesync

Apply sync operations for notes.

Headers:
- `X-API-Key: <api-key>`
- `Authorization: Bearer <access-token>`
- `Content-Type: application/json`

Example request:
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

Response:
- `results`: array of operation results with authoritative note state

Errors:
- `400 { "error": "invalid_request" }`
- `400 { "error": "invalid_base64" }`
- `401 { "error": "unauthorized" }`
