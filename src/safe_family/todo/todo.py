"""To-Do list management routes and logic."""

import logging
from datetime import UTC, datetime, time, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import get_db_connection, local_tz
from src.safe_family.core.models import LongTermGoal
from src.safe_family.notifications.notifier import (
    send_discord_notification,
    send_email_notification,
)
from src.safe_family.rules.scheduler import RULE_FUNCTIONS, load_schedules
from src.safe_family.utils.constants import Saturday

logger = logging.getLogger(__name__)
todo_bp = Blueprint("todo", __name__)


def generate_time_slots(
    slot_type: str,
    holiday: str,
    today: datetime | None = None,
) -> list[str]:
    """Return list of time slots based on weekday/weekend and duration."""
    today = today or datetime.now(local_tz)
    is_holiday = holiday == "on"
    is_weekend = today.weekday() >= Saturday

    if is_weekend or is_holiday:
        start_hour, start_minute = 9, 0
        end_hour, end_minute = 16, 0
    else:
        start_hour, start_minute = 18, 30
        end_hour, end_minute = 21, 00

    step = 30 if slot_type == "30" else 60
    slots = []

    current = datetime.strptime(f"{start_hour}:{start_minute}", "%H:%M").replace(
        tzinfo=UTC,
    )
    end = datetime.strptime(f"{end_hour}:{end_minute}", "%H:%M").replace(
        tzinfo=UTC,
    )

    logger.info(
        "Generating time slots for %s - %s",
        current,
        end,
    )
    while current < end:
        next_slot = current + timedelta(minutes=step)
        slots.append(f"{current.strftime('%H:%M')} - {next_slot.strftime('%H:%M')}")
        current = next_slot
    return slots


@todo_bp.route("/todo", methods=["GET", "POST"])
@login_required
def todo_page():
    """Render and manage the To-Do list page."""
    user = get_current_username()
    if user is None:
        flash("Please log in to access the To-Do page.", "warning")
        return redirect("/auth/login-ui")

    username = user.username
    role = user.role

    selected_user = username  # default
    # If admin, allow switching users
    if role == "admin" and request.args.get("view_user"):
        selected_user = request.args.get("view_user")

    is_holiday = request.form.get("is_holiday", "off")
    logger.info("is holiday: %s", is_holiday)

    slot_type = request.form.get("slot_type", "60")
    logger.info("slots type: %s", slot_type)

    slots = generate_time_slots(slot_type, is_holiday)
    logger.info("slots size: %d", slots.__len__())

    message = ""

    conn = get_db_connection()
    cur = conn.cursor()
    # If admin, get list of all users
    users_list = []
    if role == "admin":
        cur.execute("SELECT username FROM users ORDER BY username")
        users_list = [r[0] for r in cur.fetchall()]
    # Get selected user name
    cur.execute("SELECT username, id FROM users WHERE username = %s", (selected_user,))
    selected_user_row = cur.fetchone()
    if not selected_user_row:
        flash("Target user not found", "warning")
        selected_user = username
    selected_user_id = selected_user_row[1]
    # Save selected user's todo list
    if request.method == "POST" and "save_todo" in request.form:
        cur.execute(
            "DELETE FROM todo_list WHERE date = CURRENT_DATE AND username = %s",
            (selected_user,),
        )
        for slot in slots:
            task = request.form.get(slot, "").strip()
            logger.debug("Saving task for slot %s: %s", slot, task)
            if task:
                cur.execute(
                    "INSERT INTO todo_list (username, time_slot, task, date) VALUES (%s, %s, %s, CURRENT_DATE)",
                    (selected_user, slot, task),
                )
        conn.commit()
        message = f"Todo list saved for {selected_user} successfully."
    # Fetch today's tasks for selected user
    cur.execute(
        """
        SELECT id, time_slot, task, completed, COALESCE(completion_status, '')
        FROM todo_list
        WHERE date = CURRENT_DATE AND username = %s
        ORDER BY time_slot
        """,
        (selected_user,),
    )
    today_tasks = cur.fetchall()
    if request.method == "POST" and message != "":
        send_email_notification(
            selected_user,
            [{"time_slot": t[1], "task": t[2]} for t in today_tasks],
        )
        send_discord_notification(
            selected_user,
            [{"time_slot": r[1], "task": r[2]} for r in today_tasks],
        )
    cur.close()
    conn.close()

    now = datetime.now(local_tz).time()
    show_disable_button = today_tasks != [] and time(16, 0) <= now <= time(18, 0)

    return render_template(
        "todo/todo.html",
        user_name=username,
        role=role,
        selected_user=selected_user,
        users_list=users_list,
        slots=slots,
        slot_type=slot_type,
        is_holiday=is_holiday,
        message=message,
        today_tasks=today_tasks,
        show_disable_button=show_disable_button,
        selected_user_row_id=selected_user_id,
    )


@todo_bp.route("/update_todo/<string:selected_username>", methods=["POST"])
@login_required
def update_todo(selected_username: str):
    """Update tasks for the selected user."""
    todo_ids = request.form.getlist("todo_id")

    conn = get_db_connection()
    cur = conn.cursor()
    for todo_id in todo_ids:
        task = request.form.get(f"task_{todo_id}", "").strip()
        cur.execute(
            "UPDATE todo_list SET task = %s WHERE id = %s AND username = %s",
            (task, todo_id, selected_username),
        )
    conn.commit()
    cur.execute(
        "SELECT time_slot, task FROM todo_list WHERE date = CURRENT_DATE AND username = %s ORDER BY time_slot",
        (selected_username,),
    )
    tasks = [{"time_slot": r[0], "task": r[1]} for r in cur.fetchall()]
    send_email_notification(selected_username, tasks)
    send_discord_notification(selected_username, tasks)
    conn.close()
    flash("Task updated successfully!", "success")
    return redirect(url_for("todo.todo_page"))


@todo_bp.route(
    "/delete_todo/<string:selected_username>/<int:todo_id>",
    methods=["POST"],
)
@login_required
def delete_todo(selected_username, todo_id):
    """Delete a specific to-do item for the selected user."""
    flash(f"Deleting todo: {todo_id} for user: {selected_username}", "info")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM todo_list WHERE id = %s AND username = %s",
        (todo_id, selected_username),
    )
    conn.commit()
    conn.close()

    flash("Task deleted successfully!", "success")
    return redirect(url_for("todo.todo_page"))


@todo_bp.route(
    "/todo/mark_done",
    methods=["POST"],
)
@login_required
def done_todo():
    """Done a specific to-do item for the selected user."""
    try:
        data = request.get_json()
        todo_id = data.get("id")
        completed = data.get("completed")
        logger.info("Todo: %s is %s", todo_id, completed)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE todo_list SET completed = %s, completion_status = %s WHERE id = %s",
            (completed, "done" if completed else None, todo_id),
        )
        conn.commit()
        conn.close()

        flash("update_status successfully!", "success")
        return jsonify({"success": True})
    except Exception as e:
        flash("Error update_status:", "error")
        return jsonify({"success": False, "error": str(e)}), 500


@todo_bp.post("/todo/split_slot")
@login_required
def split_slot():
    """Split a one-hour slot into two 30-minute slots for today."""
    try:
        data = request.get_json()
        todo_id = data.get("id")
        selected_user = data.get("username")
        current_user = get_current_username()
        if current_user is None:
            return jsonify({"success": False, "error": "not authorized"}), 401

        if current_user.role != "admin" and current_user.username != selected_user:
            return jsonify({"success": False, "error": "forbidden"}), 403

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT username, time_slot, task, completed
            FROM todo_list
            WHERE id = %s AND date = CURRENT_DATE
            """,
            (todo_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "error": "not found"}), 404

        username, time_slot, task, completed = row
        if username != selected_user:
            conn.close()
            return jsonify({"success": False, "error": "user mismatch"}), 400
        if completed:
            conn.close()
            return jsonify({"success": False, "error": "already completed"}), 400

        try:
            start_str, end_str = [t.strip() for t in time_slot.split("-")]
            start_dt = datetime.strptime(start_str, "%H:%M")
            end_dt = datetime.strptime(end_str, "%H:%M")
        except (ValueError, AttributeError):
            conn.close()
            return jsonify({"success": False, "error": "invalid time slot"}), 400

        duration = end_dt - start_dt
        if duration != timedelta(minutes=60):
            conn.close()
            return jsonify({"success": False, "error": "slot not 60 minutes"}), 400

        mid_dt = start_dt + timedelta(minutes=30)
        first_slot = f"{start_dt.strftime('%H:%M')} - {mid_dt.strftime('%H:%M')}"
        second_slot = f"{mid_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"

        cur.execute(
            """
            SELECT 1
            FROM todo_list
            WHERE date = CURRENT_DATE
              AND username = %s
              AND time_slot = %s
            """,
            (username, second_slot),
        )
        if cur.fetchone():
            conn.close()
            return jsonify({"success": False, "error": "slot already exists"}), 400

        cur.execute(
            "UPDATE todo_list SET time_slot = %s WHERE id = %s",
            (first_slot, todo_id),
        )
        cur.execute(
            """
            INSERT INTO todo_list (username, time_slot, task, date, completed, completion_status)
            VALUES (%s, %s, %s, CURRENT_DATE, %s, %s)
            """,
            (username, second_slot, "", False, None),
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@todo_bp.route("/todo/mark_status", methods=["POST"])
@login_required
def mark_todo_status():
    """Store completion status feedback for a to-do item."""
    try:
        data = request.get_json()
        todo_id = data.get("id")
        status = (data.get("status") or "").strip().lower()
        allowed = {"skipped", "partially done", "mostly done", "done"}
        if status not in allowed:
            return jsonify({"success": False, "error": "invalid status"}), 400

        completed = status == "done"
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE todo_list SET completion_status = %s, completed = %s WHERE id = %s",
            (status, completed, todo_id),
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@todo_bp.route("/exec_rules/<string:selected_user_id>", methods=["POST"])
@login_required
def exec_rules(selected_user_id: str):
    """Execute assigned rules for the selected user."""
    user_id = selected_user_id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT assigned_rule FROM user_rule_assignment WHERE user_id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    rule_name = row[0] if row else None

    if not rule_name:
        flash("No rule assigned to the user.", "warning")
        return redirect(url_for("todo.todo_page"))

    func = RULE_FUNCTIONS.get(rule_name)
    if func:
        flash(f"Executing rule: {rule_name}", "info")
        try:
            func()
        except Exception as e:
            flash(f"Error executing {rule_name}: {e}", "danger")
    else:
        flash(f"Rule {rule_name} not found in RULE_FUNCTIONS.", "danger")

    # For pre-configured rule only, I want to make the network rule back in one hour later
    if rule_name == "Rule disable all":
        cur.execute(
            "UPDATE schedule_rules SET start_time = NOW() + INTERVAL '1 hour' WHERE id = 15",
        )
        conn.commit()
        load_schedules()
    conn.close()
    return redirect(url_for("todo.todo_page"))


# ──────────────────────────────
# GET all long-term tasks
# ──────────────────────────────
@todo_bp.get("/todo/long_term_list/<string:selected_user_id>")
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
@todo_bp.post("/todo/long_term_add")
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
@todo_bp.post("/todo/long_term_update")
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


@todo_bp.post("/todo/long_term_reorder")
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


@todo_bp.post("/todo/longterm_start/<int:goal_id>")
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


@todo_bp.post("/todo/longterm_stop/<int:goal_id>")
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


@todo_bp.post("/todo/longterm_update_due/<int:goal_id>")
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


@todo_bp.post("/todo/longterm_delete/<int:goal_id>")
def longterm_delete(goal_id: int):
    """Delete goal."""
    goal = LongTermGoal.query.get(goal_id)
    if goal is None:
        return jsonify({"success": False, "error": "Not found"}), 404

    goal.delete_goal()
    return jsonify({"success": True})
