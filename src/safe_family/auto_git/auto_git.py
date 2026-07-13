"""Automated Git operations for Safe Family application."""

import fnmatch
import logging
import shutil
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import psycopg2
from flask import Blueprint, flash, redirect

from config.settings import settings
from src.safe_family.core.auth import admin_required
from src.safe_family.core.extensions import get_db_connection, local_tz

logger = logging.getLogger(__name__)
auto_git_bp = Blueprint("auto_git", __name__)


def rule_auto_commit():
    """Automatically commit and push block list changes to GitHub."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT qh, type FROM block_list ORDER BY type, qh")
    rows = cur.fetchall()
    cur.execute("SELECT qh FROM filter_rule order by qh")
    rows_filter = cur.fetchall()
    conn.close()

    # Group by type

    grouped = defaultdict(list)
    for qh, type_ in rows:
        grouped[type_].append(qh)

    # Write files
    for type_, qh_list in grouped.items():
        file_path = Path(f"{settings.ADGUARD_RULE_PATH}block_{type_}.txt")
        with file_path.open("w", encoding="utf-8") as f:
            f.write(f"! Block List for type: {type_}\n")
            f.write("! Format: ||domain^ \n\n")
            for qh in qh_list:
                domain = qh.replace("%", "")
                f.write(f"||{domain}^\n")
            f.write("\n! End of Block List\n")

    filter_path = Path(f"{settings.ADGUARD_RULE_PATH}filter.txt")
    with filter_path.open("w", encoding="utf-8") as ff:
        for qh in rows_filter:
            ff.write(f"{qh[0]}\n")
        ff.write("\n")

    git_path = shutil.which("git")
    try:
        # Fixed git binary + constant args; cwd comes from settings, not user input.
        subprocess.check_call(  # noqa: S603
            [git_path, "add", "."],
            cwd=settings.ADGUARD_RULE_PATH,
        )
        commit_msg = f"Auto update block_list {datetime.now(local_tz).strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.check_call(  # noqa: S603
            [git_path, "commit", "-m", commit_msg],
            cwd=settings.ADGUARD_RULE_PATH,
        )
        subprocess.check_call([git_path, "push"], cwd=settings.ADGUARD_RULE_PATH)  # noqa: S603
    except subprocess.CalledProcessError as e:
        logger.exception("Error adding files to git: %d", e.returncode)


@auto_git_bp.route("/auto_push")
@admin_required
def auto_push():
    """Automatically commit and push block list changes to GitHub."""
    rule_auto_commit()
    flash("Block list committed and pushed to GitHub.", "success")
    return redirect("/")


@auto_git_bp.route("/auto_import")
@admin_required
def auto_import():
    """Automatically import block list from files into the database."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Look for files matching pattern like block_*.txt
    for file_path in Path().iterdir():
        file_name = file_path.name
        if fnmatch.fnmatch(file_name, "block_*.txt"):
            type_ = file_name.replace("block_", "").replace(".txt", "")
            with file_path.open(encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("!"):
                        continue
                    if line.startswith("||") and line.endswith("^"):
                        domain = line[2:-1]  # remove || and ^
                        pattern = f"%{domain}%"
                        try:
                            cur.execute(
                                "INSERT INTO block_list (qh, type) VALUES (%s, %s)",
                                (pattern, type_),
                            )
                        except psycopg2.errors.UniqueViolation:
                            conn.rollback()  # required to continue after error
    conn.commit()
    conn.close()

    flash("Block list imported from files into database.", "success")
    return redirect("/")
