CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    text TEXT NOT NULL,
    is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    deleted_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS ix_notes_user_id ON notes (user_id);
CREATE INDEX IF NOT EXISTS ix_notes_updated_at ON notes (updated_at);

CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    CONSTRAINT uq_tags_user_name UNIQUE (user_id, name)
);

CREATE INDEX IF NOT EXISTS ix_tags_user_id ON tags (user_id);

CREATE TABLE IF NOT EXISTS note_tags (
    note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

CREATE TABLE IF NOT EXISTS media (
    id TEXT PRIMARY KEY,
    note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    checksum TEXT NOT NULL,
    data BYTEA NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_media_user_id ON media (user_id);
CREATE INDEX IF NOT EXISTS ix_media_note_id ON media (note_id);

CREATE TABLE IF NOT EXISTS note_sync_ops (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    op_id TEXT NOT NULL,
    note_id TEXT NOT NULL,
    result TEXT NOT NULL,
    applied_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_notesync_user_op UNIQUE (user_id, op_id)
);

CREATE INDEX IF NOT EXISTS ix_note_sync_ops_user_id ON note_sync_ops (user_id);
CREATE INDEX IF NOT EXISTS ix_note_sync_ops_note_id ON note_sync_ops (note_id);

CREATE TABLE IF NOT EXISTS auth_codes (
    id SERIAL PRIMARY KEY,
    code_hash VARCHAR(64) NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used_at TIMESTAMP NULL
);

CREATE INDEX IF NOT EXISTS ix_auth_codes_user_id ON auth_codes (user_id);
