"""One-off schema migrations for raw-SQL tables.

Run inside the app environment: python scripts/migrate.py
"""

from src.safe_family.core.extensions import get_db_connection

MIGRATIONS = [
    # Speeds up per-user history scans (week strip / activity heatmap on /todo)
    # and the existing per-day lookups.
    """
    CREATE INDEX IF NOT EXISTS idx_todo_list_username_date
        ON todo_list (username, date)
    """,
    # Per-user countdown page settings (see CountdownConfig ORM model)
    """
    CREATE TABLE IF NOT EXISTS countdown_config (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR UNIQUE NOT NULL,
        target_date VARCHAR(10) NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        updated_at TIMESTAMP
    )
    """,
    # Audit trail for filter rules. Added without a default first so rows that
    # predate the column stay NULL (unknown) instead of all getting the
    # migration time; new rows get now().
    """
    ALTER TABLE filter_rule ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE filter_rule ALTER COLUMN created_at SET DEFAULT now()
    """,
    # Weekly audit matrix on /todo (see AuditItem / AuditMark ORM models).
    # Admins add more rows with:
    #   INSERT INTO audit_item (name, sort_order) VALUES ('Reading', 4);
    """
    CREATE TABLE IF NOT EXISTS audit_item (
        id SERIAL PRIMARY KEY,
        name VARCHAR(100) UNIQUE NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT now()
    )
    """,
    """
    INSERT INTO audit_item (name, sort_order)
    VALUES ('Piano', 1), ('Math', 2), ('Hang Socks', 3)
    ON CONFLICT (name) DO NOTHING
    """,
    # One row per (item, user, day); a missing row means the cell is null.
    """
    CREATE TABLE IF NOT EXISTS audit_mark (
        id SERIAL PRIMARY KEY,
        item_id INTEGER NOT NULL REFERENCES audit_item (id) ON DELETE CASCADE,
        user_id VARCHAR NOT NULL,
        mark_date DATE NOT NULL,
        value VARCHAR(3) NOT NULL CHECK (value IN ('yes', 'no')),
        updated_at TIMESTAMP,
        CONSTRAINT uq_audit_mark_item_user_date UNIQUE (item_id, user_id, mark_date)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_mark_user_date
        ON audit_mark (user_id, mark_date)
    """,
    # Technical blog (see BlogPost / BlogTag ORM models). The original Markdown
    # is stored as-is; HTML is rendered on read.
    """
    CREATE TABLE IF NOT EXISTS blog_posts (
        id VARCHAR PRIMARY KEY,
        user_id VARCHAR NOT NULL,
        title VARCHAR(200) NOT NULL,
        markdown TEXT NOT NULL DEFAULT '',
        is_public BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_blog_posts_user_id ON blog_posts (user_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_blog_posts_created_at ON blog_posts (created_at)
    """,
    """
    CREATE TABLE IF NOT EXISTS blog_tags (
        id VARCHAR PRIMARY KEY,
        user_id VARCHAR NOT NULL,
        name VARCHAR(64) NOT NULL,
        CONSTRAINT uq_blog_tags_user_name UNIQUE (user_id, name)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_blog_tags_user_id ON blog_tags (user_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS blog_post_tags (
        post_id VARCHAR NOT NULL REFERENCES blog_posts (id) ON DELETE CASCADE,
        tag_id VARCHAR NOT NULL REFERENCES blog_tags (id) ON DELETE CASCADE,
        PRIMARY KEY (post_id, tag_id)
    )
    """,
]


def main() -> None:
    """Run all pending raw-SQL migrations."""
    conn = get_db_connection()
    cur = conn.cursor()
    for statement in MIGRATIONS:
        cur.execute(statement)
    conn.commit()
    cur.close()
    conn.close()
    print(f"Applied {len(MIGRATIONS)} migration(s).")


if __name__ == "__main__":
    main()
