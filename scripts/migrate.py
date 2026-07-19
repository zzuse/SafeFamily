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
