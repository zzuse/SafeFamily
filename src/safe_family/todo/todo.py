"""To-Do list management routes and logic."""

import logging
from datetime import UTC, datetime, time, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import get_db_connection, local_tz
from src.safe_family.notifications.notifier import (
    send_admin_notification,
    send_discord_notification,
)
from src.safe_family.rules.scheduler import RULE_FUNCTIONS
from src.safe_family.utils.constants import Saturday

logger = logging.getLogger(__name__)
todo_bp = Blueprint("todo", __name__)


def generate_time_slots(slot_type: str, is_holiday: bool = False) -> list[str]:
    """Return list of time slots based on weekday/weekend and duration."""
    today = datetime.now(local_tz).today()
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

    slots = generate_time_slots(slot_type, is_holiday == "on")
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
        "SELECT id, time_slot, task FROM todo_list WHERE date = CURRENT_DATE AND username = %s ORDER BY time_slot",
        (selected_user,),
    )
    today_tasks = cur.fetchall()
    if request.method == "POST" and message != "":
        send_admin_notification(
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
        selected_user_row_id=selected_user_row[1],
    )


@todo_bp.route("/update_todo/<string:selected_username>", methods=["POST"])
@login_required
def update_todo(selected_username):
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
    send_admin_notification(selected_username, tasks)
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


@todo_bp.route("/exec_rules/<string:selected_user_row_id>", methods=["POST"])
@login_required
def exec_rules(selected_user_row_id):
    """Execute assigned rules for the selected user."""
    user_id = selected_user_row_id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT assigned_rule FROM user_rule_assignment WHERE user_id = %s",
        (user_id,),
    )
    row = cur.fetchone()
    rule_name = row[0] if row else None
    conn.close()

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
    return redirect(url_for("todo.todo_page"))
