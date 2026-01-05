# CLI wrapper with __main__
# python3 -m safe_family.cli.gentags -v
"""CLI for tag analysis."""

import argparse
import logging
import sys

from src.safe_family.core.extensions import get_db_connection

logger = logging.getLogger(__name__)

KEYWORDS = {
    "math": ["math", "algebra", "calculus", "tutor"],
    "science": ["science", "biology", "chemistry", "physics", "lab"],
    "language": [
        "english",
        "essay",
        "read",
        "reading",
        "history",
        "geography",
        "economics",
        "writing",
        "french",
        "francais",
        "langue",
        "spanish",
        "espanol",
        "khan",
    ],
    "coding": [
        "unity",
        "python",
        "c++",
        "js",
        "twinery",
        "roblox",
        "dev",
        "gemini",
        "game",
    ],
    "leasure": [
        "sleep",
        "clean",
        "eat",
        "exercise",
        "meditate",
        "rest",
        "snow",
        "tok",
        "sledding",
        "phone",
    ],
    "piano": ["piano", "flute", "violin"],
}


def infer_tag(task_name: str) -> str:
    """Task name to tag inference."""
    task_lower = task_name.lower()
    for tag, words in KEYWORDS.items():
        if any(w.lower() in task_lower for w in words):
            logger.debug("Inferred tag '%s' for task '%s'", tag, task_name)
            return tag
    return "unknown"


def main(args: list[str] = None) -> int:
    """Generate tags for tasks."""
    parser = argparse.ArgumentParser(
        description="Analyze URLs for safety and metadata",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parsed_args = parser.parse_args(args)
    if parsed_args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT task, id from todo_list WHERE tags IS NULL OR tags = '' OR tags = 'unknown'",
    )
    for task_name, task_id in cur.fetchall():
        inferred_tag = infer_tag(task_name)
        logger.info("Inferred tag '%s' for task '%s'", inferred_tag, task_name)
        cur.execute(
            "UPDATE todo_list SET tags = %s WHERE id = %s",
            (inferred_tag, task_id),
        )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
