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
]


def main() -> None:
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
