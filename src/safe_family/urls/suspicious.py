"""Suspicious URL routes for admin interface."""

import logging
from datetime import datetime, timedelta

import psycopg2
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
)

from src.safe_family.core.auth import admin_required
from src.safe_family.core.extensions import get_db_connection, local_tz
from src.safe_family.utils.exceptions import DatabaseConnectionError

suspicious_bp = Blueprint("suspicious", __name__)
logger = logging.getLogger(__name__)


@suspicious_bp.route("/suspicious", methods=["GET"])
@admin_required
def view_suspicious():
    """View suspicious URLs that are not in the block list.

    This route retrieves suspicious URLs from the database that are not
    present in the block list. It supports pagination for both the main
    suspicious URLs table and the block list sidebar. It also allows searching
    for specific URLs in the block list and filter rules.
    The suspicious URLs are filtered by a specific date, and the results are
    """
    page = int(request.args.get("page", 1))
    block_page = int(request.args.get("block_page", 1))
    rule_page = int(request.args.get("rule_page", 1))
    search_query = request.args.get("search", "").strip()

    date = request.args.get("date")
    if date is None:
        date = datetime.now(local_tz).strftime("%Y-%m-%d")
    error = request.args.get("error")

    limit = 10
    offset = (page - 1) * limit

    block_limit = 20  # for block_list sidebar
    block_offset = (block_page - 1) * block_limit

    rule_limit = 10  # for filter_rule below main table
    rule_offset = (rule_page - 1) * rule_limit

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """SELECT COUNT(*) FROM suspicious s
            WHERE s.date = %s
            AND NOT EXISTS (
                SELECT 1
                FROM block_list b
                WHERE s.qh LIKE b.qh
            )""",
            (date,),
        )
        total = cur.fetchone()[0]

        cur.execute(
            """
            SELECT * FROM suspicious s
            WHERE s.date = %s
            AND NOT EXISTS (
                SELECT 1
                FROM block_list b
                WHERE s.qh LIKE b.qh
            )
            ORDER BY count DESC
            LIMIT %s OFFSET %s""",
            (date, limit, offset),
        )
        suspicious_data = cur.fetchall()

        cur.execute("SELECT COUNT(*) FROM block_list")
        total_blocks = cur.fetchone()[0]
        if search_query:
            cur.execute(
                "SELECT * FROM block_list WHERE qh ILIKE %s",
                (f"%{search_query}%",),
            )
        else:
            cur.execute(
                "SELECT * FROM block_list ORDER BY id DESC LIMIT %s OFFSET %s",
                (block_limit, block_offset),
            )
        block_list = cur.fetchall()

        cur.execute("SELECT COUNT(*) FROM filter_rule")
        total_rules = cur.fetchone()[0]
        if search_query:
            cur.execute(
                "SELECT * FROM filter_rule WHERE qh ILIKE %s",
                (f"%{search_query}%",),
            )
        else:
            cur.execute(
                "SELECT * FROM filter_rule ORDER BY qh LIMIT %s OFFSET %s",
                (rule_limit, rule_offset),
            )
        filter_rules = cur.fetchall()

        cur.execute("SELECT name FROM block_types ORDER BY name")
        block_types = [row[0] for row in cur.fetchall()]

        # Check for yesterday's logs (local time) as the scheduler runs on completed days
        yesterday_local = (datetime.now(local_tz) - timedelta(days=1)).date()
        cur.execute("SELECT COUNT(*) FROM logs_daily WHERE date = %s", (yesterday_local,))
        count_yesterday = cur.fetchone()[0]

        if count_yesterday == 0:
            flash(f"⚠️ Warning: No logs found in logs_daily for yesterday ({yesterday_local}).", "danger")

        cur.close()
        conn.close()

        return render_template(
            "rules/suspicious_view.html",
            suspicious_data=suspicious_data,
            block_list=block_list,
            filter_rules=filter_rules,
            page=page,
            total=total,
            limit=limit,
            block_page=block_page,
            total_blocks=total_blocks,
            block_limit=block_limit,
            rule_page=rule_page,
            total_rules=total_rules,
            rule_limit=rule_limit,
            block_types=block_types,
            date=date,
            error=error,
        )
    except DatabaseConnectionError as e:
        logger.exception("Error viewing suspicious")
        return f"Error: {e}", 500


@suspicious_bp.route("/update_filter_rule", methods=["POST"])
@admin_required
def update_filter_rule():
    """Update filter rules based on user input.

    This route allows users to modify existing filter rules for suspicious URLs.
    """
    raw_text = request.form.getlist("rule")
    date = request.form.get("date", "")
    rules = [line.strip() for line in raw_text if line.strip()]

    if not rules:
        return redirect("suspicious?date=" + date)

    conn = get_db_connection()
    cur = conn.cursor()

    error = None
    try:
        for rule in rules:
            logger.info(rule)
            try:
                cur.execute("INSERT INTO filter_rule VALUES (%s)", (rule.strip(),))
            except psycopg2.Error as insert_error:
                error = f"Insert error for '{rule}': {insert_error.pgerror}"
                logger.exception(error)
                break
        conn.commit()
    except DatabaseConnectionError as e:
        conn.rollback()
        error = f"Unexpected filter_rule: {e!s}"
        logger.exception(error)
    finally:
        cur.close()
        conn.close()

    if error:
        error = error.replace("\n", " | ")
        return redirect(f"/suspicious?date={date}&error={error}")
    return redirect("/suspicious?date=" + date)


@suspicious_bp.route("/delete_filter_rule/<rule>", methods=["POST"])
@admin_required
def delete_filter_rule(rule: str):
    """Delete a filter rule based on user input.

    This route allows users to remove existing filter rules for suspicious URLs.

    Args:
        rule (str): The filter rule to delete.

    Returns:
        Redirect to the suspicious URLs view with the current date.


    """
    date = request.args.get("date", datetime.today().strftime("%Y-%m-%d"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM filter_rule WHERE qh = %s", (rule,))
    conn.commit()
    conn.close()

    flash("Filter rule deleted.", "info")
    return redirect(f"/suspicious?date={date}")


@suspicious_bp.route("/tag_block", methods=["POST"])
def tag_block():
    """Tag a suspicious URL as blocked. This route allows users to modify existing block rules for suspicious URLs."""
    qh = request.form.get("qh")
    type_ = request.form.get("type")
    date = request.form.get("date")
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO block_list (qh, type) VALUES (%s, %s)", (qh, type_))
        conn.commit()
        flash(f"Tagged '{qh}' as '{type_}' successfully.", "success")
    except DatabaseConnectionError:
        flash(
            f"Error: Could not insert '{qh}' — it may already exist in block list.",
            "danger",
        )
    finally:
        cur.close()
        conn.close()
    return redirect(f"/suspicious?date={date}")


@suspicious_bp.route("/add_block", methods=["POST"])
@admin_required
def add_block():
    """Add a URL to the block list.

    This route allows users to add new block rules for suspicious URLs.
    """
    date = request.args.get("date", datetime.today().strftime("%Y-%m-%d"))
    qh = request.form.get("qh").strip()
    type_ = request.form.get("type").strip()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO block_list (qh, type) VALUES (%s, %s)", (qh, type_))
        conn.commit()
        cur.close()
        conn.close()
    except DatabaseConnectionError:
        logger.exception("Add block error")
    return redirect(f"/suspicious?date={date}")


@suspicious_bp.route("/delete_block/<int:block_id>")
@admin_required
def delete_block(block_id: int):
    """Delete a block rule based on user input.

    This route allows users to remove existing block rules for suspicious URLs.

    Args:
        block_id (int): The ID of the block rule to delete.

    Returns:
        Redirect to the suspicious URLs view with the current date.

    """
    date = request.args.get("date", datetime.today().strftime("%Y-%m-%d"))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM block_list WHERE id = %s", (block_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(f"/suspicious?date={date}")


@suspicious_bp.route("/modify_block/<int:block_id>", methods=["POST"])
@admin_required
def modify_block(block_id: int):
    """Update block rules based on user input.

    This route allows users to modify existing block rules for suspicious URLs.

    Args:
        block_id (int): The ID of the block rule to modify.
        request: The Flask request object containing form data with 'qh' and 'type'.

    Returns:
        Redirect to the suspicious URLs view with the current date.

    """
    qh = request.form["qh"]
    type_ = request.form["type"]
    date = request.args.get("date", datetime.today().strftime("%Y-%m-%d"))

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE block_list SET qh = %s, type = %s WHERE id = %s",
            (qh, type_, block_id),
        )
        conn.commit()
        flash("Block list entry updated.", "success")
    except DatabaseConnectionError as e:
        flash(f"Failed to update block list entry: {e!s}", "danger")
    finally:
        conn.close()

    return redirect(f"/suspicious?date={date}")
