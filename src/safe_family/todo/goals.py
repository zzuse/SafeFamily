"""Long-term goals management routes and logic."""

import logging
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request

from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import get_db_connection, local_tz
from src.safe_family.core.models import LongTermGoal

logger = logging.getLogger(__name__)
goals_bp = Blueprint("goals", __name__)


@goals_bp.route("/goals", methods=["GET"])
@login_required
def goals_page():
    """Render the long-term goals page."""
    user = get_current_username()
    if user is None:
        flash("Please log in to access the Goals page.", "warning")
        return redirect("/auth/login-ui")

    username = user.username
    role = user.role

    selected_user = username
    if role == "admin" and request.args.get("view_user"):
        selected_user = request.args.get("view_user")

    conn = get_db_connection()
    cur = conn.cursor()
    
    # Get selected user ID
    cur.execute("SELECT id FROM users WHERE username = %s", (selected_user,))
    selected_user_row = cur.fetchone()
    if not selected_user_row:
        flash("Target user not found", "warning")
        selected_user = username
        cur.execute("SELECT id FROM users WHERE username = %s", (selected_user,))
        selected_user_row = cur.fetchone()
    
    selected_user_id = selected_user_row[0]
    cur.close()
    conn.close()

    return render_template(
        "todo/goals.html",
        user_name=username,
        role=role,
        selected_user=selected_user,
        selected_user_row_id=selected_user_id,
    )


# ──────────────────────────────
# GET all long-term tasks
# ──────────────────────────────
@goals_bp.get("/todo/long_term_list/<string:selected_user_id>")
@login_required
def get_long_term(selected_user_id: str):
    """Get all long-term tasks for the selected user."""
    user_id = selected_user_id
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT goal_id, task_text, priority, completed, to_char(due_date, 'YYYY-MM-DD"T"HH24:MI:SS') AS datetime_local, time_spent, is_tracking
        FROM long_term_goals
        WHERE user_id = %s
        ORDER BY priority ASC, goal_id DESC
    """,
        (user_id,),
    )
    rows = cur.fetchall()
    if rows:
        logger.info("Long-term tasks: %s", rows[0])
    conn.close()

    return jsonify(
        [
            {
                "goal_id": r[0],
                "task": r[1],
                "priority": r[2],
                "completed": r[3],
                "due_date": r[4],
                "time_spent": r[5],
                "is_tracking": r[6],
            }
            for r in rows
        ],
    )


# ──────────────────────────────
# ADD long-term task
# ──────────────────────────────
@goals_bp.post("/todo/long_term_add")
@login_required
def add_long_term():
    """Add a new long-term task for the selected user."""
    data = request.get_json()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO long_term_goals (user_id, task_text, priority)
        VALUES (%s, %s, %s)
    """,
        (data["user_id"], data["task"], data["priority"]),
    )

    conn.commit()
    conn.close()

    return jsonify({"success": True})


# ──────────────────────────────
# UPDATE completion or priority
# ──────────────────────────────
@goals_bp.post("/todo/long_term_update")
@login_required
def update_long_term_complete():
    """Update long-term task's completion status or priority."""
    data = request.get_json()

    conn = get_db_connection()
    cur = conn.cursor()
    completed_at = None
    logger.debug("Updating long-term task: %s", data)
    if data["completed"]:
        completed_at = datetime.now(local_tz)
        data["priority"] = data["color_length"] + 1
    cur.execute(
        """
        UPDATE long_term_goals
        SET task_text = %s, priority = %s, completed = %s, completed_at = %s
        WHERE goal_id = %s
    """,
        (
            data["task"],
            data["priority"],
            data["completed"],
            completed_at,
            data["goal_id"],
        ),
    )

    conn.commit()
    conn.close()

    return jsonify({"success": True})


@goals_bp.post("/todo/long_term_reorder")
@login_required
def reorder_long_term():
    """Reorder long-term tasks based on provided list of IDs."""
    data = request.get_json()
    id_list = data["order"]

    conn = get_db_connection()
    cur = conn.cursor()

    # priority 1 = top item
    for index, goal_id in enumerate(id_list, start=1):
        cur.execute(
            "UPDATE long_term_goals SET priority = %s WHERE goal_id = %s",
            (index, goal_id),
        )

    conn.commit()
    conn.close()

    return jsonify({"status": "ok"})


@goals_bp.post("/todo/longterm_start/<int:goal_id>")
@login_required
def start_goal_tracking(goal_id: int):
    """Start goal tracking."""
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE long_term_goals
        SET is_tracking = TRUE,
            tracking_start = NOW()
        WHERE goal_id = %s AND is_tracking = FALSE
    """,
        (goal_id,),
    )

    conn.commit()
    conn.close()

    return jsonify({"status": "started"})


@goals_bp.post("/todo/longterm_stop/<int:goal_id>")
@login_required
def stop_goal_tracking(goal_id: int):
    """Stop goal tracking."""
    goal = LongTermGoal.query.get(goal_id)

    if not goal.tracking_start:
        return jsonify({"error": "not tracking"}), 400

    goal = goal.stop_tracking()

    return jsonify(
        {
            "status": "stopped",
            "time_spent": goal.time_spent,
        },
    )


@goals_bp.post("/todo/longterm_update_due/<int:goal_id>")
def update_due(goal_id: int):
    """Update long-term task's due date."""
    due = request.json.get("due_date")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE long_term_goals
        SET due_date = %s
        WHERE goal_id = %s
    """,
        (due, goal_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})


@goals_bp.post("/todo/longterm_delete/<int:goal_id>")
def longterm_delete(goal_id: int):
    """Delete goal."""
    goal = LongTermGoal.query.get(goal_id)
    if goal is None:
        return jsonify({"success": False, "error": "Not found"}), 404

    goal.delete_goal()
    return jsonify({"success": True})
