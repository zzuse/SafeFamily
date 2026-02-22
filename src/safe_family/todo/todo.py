"""To-Do list management routes and logic."""

import logging
import threading
import time as time_module
from datetime import UTC, datetime, time, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from src.safe_family.cli import gentags, weekly_diff, weekly_metrics
from src.safe_family.core.auth import get_current_username, login_required
from src.safe_family.core.extensions import get_db_connection, local_tz
from src.safe_family.notifications.notifier import (
    send_discord_notification,
    send_discord_summary,
    send_email_notification,
    send_hammerspoon_alert,
    send_hammerspoon_task,
)
from src.safe_family.rules.scheduler import (
    RULE_FUNCTIONS,
    load_schedules,
    notify_schedule_change,
)
from src.safe_family.utils.constants import Saturday

logger = logging.getLogger(__name__)
todo_bp = Blueprint("todo", __name__)
RULE_EXEC_LOCK = threading.Lock()
RULE_EXEC_COOLDOWN_SECONDS = 30.0
RULE_EXEC_STATE = {"last_run": 0.0}


def generate_time_slots(
    slot_type: str,
    schedule_mode: str,
    custom_start: str,
    custom_end: str,
    today: datetime | None = None,
) -> list[str]:
    """Return list of time slots based on weekday/weekend and duration."""
    today = today or datetime.now(local_tz)
    is_weekend = today.weekday() >= Saturday

    if schedule_mode == "custom":
        try:
            start_parts = [int(p) for p in custom_start.split(":")]
            end_parts = [int(p) for p in custom_end.split(":")]
            if len(start_parts) != 2 or len(end_parts) != 2:
                raise ValueError("invalid time format")
            start_hour, start_minute = start_parts
            end_hour, end_minute = end_parts
            start_time = time(start_hour, start_minute)
            end_time = time(end_hour, end_minute)
            if end_time <= start_time:
                raise ValueError("invalid time range")
        except (TypeError, ValueError):
            logger.warning(
                "Invalid custom time range: %s - %s; falling back to weekday hours",
                custom_start,
                custom_end,
            )
            schedule_mode = "weekday"

    if schedule_mode != "custom":
        if schedule_mode == "holiday" or is_weekend:
            start_hour, start_minute = 9, 0
            end_hour, end_minute = 16, 0
        else:
            start_hour, start_minute = 18, 30
            end_hour, end_minute = 21, 30

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
        if next_slot < end:
            slots.append(f"{current.strftime('%H:%M')} - {next_slot.strftime('%H:%M')}")
        else:
            slots.append(f"{current.strftime('%H:%M')} - {end.strftime('%H:%M')}")
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

    schedule_mode = request.form.get("schedule_mode", "weekday")
    logger.info("schedule mode: %s", schedule_mode)

    slot_type = request.form.get("slot_type", "60")
    logger.info("slots type: %s", slot_type)

    custom_start = request.form.get("custom_start", "")
    custom_end = request.form.get("custom_end", "")
    if schedule_mode == "custom" and (not custom_start or not custom_end):
        custom_start = custom_start or "18:30"
        custom_end = custom_end or "21:00"

    slots = generate_time_slots(
        slot_type,
        schedule_mode,
        custom_start,
        custom_end,
    )
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
    today_date = datetime.now(local_tz).date()

    # Save selected user's todo list
    if request.method == "POST" and "save_todo" in request.form:
        cur.execute(
            "DELETE FROM todo_list WHERE date = %s AND username = %s",
            (today_date, selected_user),
        )
        for slot in slots:
            task = request.form.get(slot, "").strip()
            logger.debug("Saving task for slot %s: %s", slot, task)
            if task:
                cur.execute(
                    "INSERT INTO todo_list (username, time_slot, task, date) VALUES (%s, %s, %s, %s)",
                    (selected_user, slot, task, today_date),
                )
        conn.commit()
        message = f"Todo list saved for {selected_user} successfully."
    # Fetch today's tasks for selected user
    cur.execute(
        """
        SELECT id, time_slot, task, completed, COALESCE(completion_status, '')
        FROM todo_list
        WHERE date = %s AND username = %s
        ORDER BY time_slot
        """,
        (today_date, selected_user),
    )
    today_tasks = cur.fetchall()
    if request.method == "POST" and message != "":
        send_email_notification(
            selected_user,
            [{"time_slot": t[1], "task": t[2]} for t in today_tasks],
        )
        send_discord_notification(
            selected_user,
            [
                {
                    "time_slot": r[1],
                    "task": r[2],
                    "completion_status": r[4],
                }
                for r in today_tasks
            ],
        )
    cur.close()
    conn.close()

    now = datetime.now(local_tz).time()
    show_disable_button = (today_tasks != [] and time(16, 0) <= now <= time(18, 0)) or (
        role == "admin"
    )
    show_task_feedback = not (role == "admin" and selected_user != username)

    return render_template(
        "todo/todo.html",
        user_name=username,
        role=role,
        selected_user=selected_user,
        users_list=users_list,
        slots=slots,
        slot_type=slot_type,
        schedule_mode=schedule_mode,
        custom_start=custom_start,
        custom_end=custom_end,
        message=message,
        today_tasks=today_tasks,
        show_disable_button=show_disable_button,
        selected_user_row_id=selected_user_id,
        show_task_feedback=show_task_feedback,
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
    today_date = datetime.now(local_tz).date()
    cur.execute(
        """
        SELECT time_slot, task, COALESCE(completion_status, '')
        FROM todo_list
        WHERE date = %s AND username = %s
        ORDER BY time_slot
        """,
        (today_date, selected_username),
    )
    tasks = [
        {"time_slot": r[0], "task": r[1], "completion_status": r[2]}
        for r in cur.fetchall()
    ]
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
    """Automatic mark completed for to-do item for the selected user."""
    try:
        data = request.get_json()
        todo_id = data.get("id")
        completed = data.get("completed")
        logger.info("Todo: %s is %s", todo_id, completed)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT time_slot FROM todo_list WHERE id = %s",
            (todo_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "error": "not found"}), 404

        time_slot = row[0]
        try:
            _, end_str = [t.strip() for t in time_slot.split("-")]
            end_time = datetime.strptime(end_str, "%H:%M").time()
        except (ValueError, AttributeError):
            conn.close()
            return jsonify({"success": False, "error": "invalid time slot"}), 400

        now = datetime.now(local_tz)
        end_dt = now.replace(
            hour=end_time.hour,
            minute=end_time.minute,
            second=0,
            microsecond=0,
        )
        if now >= end_dt and completed is False:
            completed = True

        cur.execute(
            "UPDATE todo_list SET completed = %s WHERE id = %s",
            (completed, todo_id),
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
        today_date = datetime.now(local_tz).date()
        cur.execute(
            """
            SELECT username, time_slot, task, completed
            FROM todo_list
            WHERE id = %s AND date = %s
            """,
            (todo_id, today_date),
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
        if duration != timedelta(minutes=60) and duration != timedelta(minutes=59):
            conn.close()
            return jsonify({"success": False, "error": "slot not 60 minutes"}), 400

        mid_dt = start_dt + timedelta(minutes=30)
        first_slot = f"{start_dt.strftime('%H:%M')} - {mid_dt.strftime('%H:%M')}"
        second_slot = f"{mid_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"

        cur.execute(
            """
            SELECT 1
            FROM todo_list
            WHERE date = %s
              AND username = %s
              AND time_slot = %s
            """,
            (today_date, username, second_slot),
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
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (username, second_slot, "", today_date, False, None),
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
        user = get_current_username()
        logger.info(
            "mark_status request: user=%s json=%s content_type=%s path=%s",
            getattr(user, "username", None),
            request.is_json,
            request.content_type,
            request.path,
        )
        try:
            data = request.get_json()
        except Exception:
            logger.exception("mark_status: invalid json payload")
            raise
        todo_id = data.get("id")
        status = (data.get("status") or "").strip().lower()
        allowed = {"skipped", "partially done", "half done", "mostly done", "done"}
        if status not in allowed:
            logger.warning("mark_status: invalid status id=%s status=%s", todo_id, status)
            return jsonify({"success": False, "error": "invalid status"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT completion_status, time_slot, username, task, to_char(date, 'YYYY-MM-DD HH24:MI:SS') FROM todo_list WHERE id = %s",
            (todo_id,),
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            logger.warning("mark_status: not found id=%s", todo_id)
            return jsonify({"success": False, "error": "not found"}), 404

        existing_status, time_slot, task_owner, task_name, log_date = row
        is_admin = user is not None and user.role == "admin"
        if existing_status and not is_admin:
            conn.close()
            logger.warning("mark_status: status locked id=%s user=%s", todo_id, user)
            return jsonify({"success": False, "error": "status locked"}), 401

        logger.debug("Marking todo id %s with status %s", todo_id, status)

        try:
            _, end_str = [t.strip() for t in time_slot.split("-")]
            end_time = datetime.strptime(end_str, "%H:%M").time()
        except (ValueError, AttributeError):
            conn.close()
            logger.warning("mark_status: invalid time slot id=%s time_slot=%s", todo_id, time_slot)
            return jsonify({"success": False, "error": "invalid time slot"}), 402

        now = datetime.now(local_tz)
        log_date_naive = datetime.fromisoformat(log_date)
        log_date_dt = local_tz.localize(log_date_naive)
        end_dt_naive = datetime.combine(log_date_naive.date(), end_time)
        end_dt = local_tz.localize(end_dt_naive)
        if now < end_dt and not is_admin:
            conn.close()
            logger.warning("mark_status: too early id=%s now=%s end=%s", todo_id, now, end_dt)
            return jsonify({"success": False, "error": "too early"}), 403

        cur.execute(
            "UPDATE todo_list SET completion_status = %s, completed = %s WHERE id = %s",
            (status, True, todo_id),
        )
        conn.commit()
        send_discord_notification(
            task_owner,
            [
                {
                    "time_slot": time_slot,
                    "task": task_name,
                    "completion_status": status,
                },
            ],
        )
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@todo_bp.post("/todo/notify_feedback")
@login_required
def notify_feedback():
    """Send a local desktop alert when task feedback is due."""
    data = request.get_json() or {}
    time_slot = (data.get("time_slot") or "").strip()
    task = (data.get("task") or "").strip()

    if time_slot and task:
        message = f"{time_slot} - {task}"
    else:
        message = time_slot or task or "Task feedback needed"

    send_hammerspoon_alert(message)
    return jsonify({"success": True})


@todo_bp.post("/todo/notify_current_task")
@login_required
def notify_current_task():
    """Send a local desktop alert for the current time slot task."""
    user = get_current_username()
    if user is None:
        return jsonify({"success": False, "error": "not logged in"}), 401

    data = request.get_json() or {}
    requested_user = (data.get("username") or "").strip()
    target_username = user.username
    if requested_user:
        if user.role != "admin" and requested_user != user.username:
            return jsonify({"success": False, "error": "forbidden"}), 403
        target_username = requested_user

    now = datetime.now(local_tz)
    conn = get_db_connection()
    cur = conn.cursor()
    today_date = now.date()
    cur.execute(
        """
        SELECT time_slot, task
        FROM todo_list
        WHERE date = %s
          AND username = %s
          AND COALESCE(task, '') <> ''
        ORDER BY time_slot
        """,
        (today_date, target_username),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    current_task = None
    for time_slot, task in rows:
        try:
            start_str, end_str = [t.strip() for t in time_slot.split("-")]
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()
        except (ValueError, AttributeError):
            continue

        start_dt = now.replace(
            hour=start_time.hour,
            minute=start_time.minute,
            second=0,
            microsecond=0,
        )
        end_dt = now.replace(
            hour=end_time.hour,
            minute=end_time.minute,
            second=0,
            microsecond=0,
        )
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        if start_dt <= now < end_dt:
            current_task = (time_slot, task)
            break

    if not current_task:
        return jsonify({"success": False, "error": "no current task"}), 404

    time_slot, task_name = current_task
    send_hammerspoon_task(target_username, task_name, time_slot)
    return jsonify(
        {
            "success": True,
            "username": target_username,
            "time_slot": time_slot,
            "task": task_name,
        },
    )


@todo_bp.get("/todo/weekly_summary")
@login_required
def weekly_summary():
    """Return a weekly summary for the current or selected user."""
    user = get_current_username()
    if user is None:
        return jsonify({"success": False, "error": "not logged in"}), 401

    requested_user = (request.args.get("user") or "").strip()
    username = user.username
    if user.role == "admin" and requested_user:
        username = requested_user

    gentags.main([])

    today = datetime.now(local_tz).date()
    current_iso = today.isocalendar()
    current_week = f"{current_iso.year}-W{current_iso.week:02d}"
    previous_date = today - timedelta(days=7)
    previous_iso = previous_date.isocalendar()
    previous_week = f"{previous_iso.year}-W{previous_iso.week:02d}"

    current_start, current_end = weekly_metrics._parse_iso_week(current_week)
    previous_start, previous_end = weekly_metrics._parse_iso_week(previous_week)

    current_df = weekly_metrics._fetch_week_df(current_start, current_end, username)
    previous_df = weekly_metrics._fetch_week_df(previous_start, previous_end, username)
    current_metrics = weekly_metrics._compute_metrics(
        current_df,
        current_start,
        current_end,
    )
    previous_metrics = weekly_metrics._compute_metrics(
        previous_df,
        previous_start,
        previous_end,
    )

    current_payload = weekly_diff.WeekMetrics(
        week=current_week,
        completion_rate=current_metrics.completion_rate,
        avg_tasks_per_day=current_metrics.avg_tasks_per_day,
        avg_planned_minutes=current_metrics.avg_planned_minutes,
        by_category=current_metrics.by_category,
        by_category_minutes=current_metrics.by_category_minutes,
    )
    previous_payload = weekly_diff.WeekMetrics(
        week=previous_week,
        completion_rate=previous_metrics.completion_rate,
        avg_tasks_per_day=previous_metrics.avg_tasks_per_day,
        avg_planned_minutes=previous_metrics.avg_planned_minutes,
        by_category=previous_metrics.by_category,
        by_category_minutes=previous_metrics.by_category_minutes,
    )

    summary = weekly_diff._format_output(current_payload, previous_payload)
    send_discord_summary(username, summary, current_week, previous_week)
    return jsonify(
        {
            "success": True,
            "summary": summary,
            "week": current_week,
            "previous_week": previous_week,
        },
    )


@todo_bp.get("/todo/unknown_metadata")
@login_required
def unknown_metadata():
    """Return tasks with unknown tags or missing completion status."""
    user = get_current_username()
    if user is None:
        return jsonify({"success": False, "error": "not logged in"}), 401

    requested_user = (request.args.get("user") or "").strip()
    username = user.username
    if user.role == "admin" and requested_user:
        username = requested_user

    gentags.main([])

    conn = get_db_connection()
    cur = conn.cursor()
    today_date = datetime.now(local_tz).date()
    cur.execute(
        """
        SELECT id, time_slot, task, tags, date, completion_status
        FROM todo_list
        WHERE username = %s
          AND date <= %s
          AND (tags IS NULL OR tags = '' OR tags = 'unknown' OR completion_status IS NULL OR completion_status = '')
        ORDER BY date DESC, time_slot
        """,
        (username, today_date),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    today = today_date
    now = datetime.now(local_tz)
    unknown_tags = []
    unknown_status = []
    for todo_id, time_slot, task, tags, task_date, completion_status in rows:
        tag_missing = (
            tags is None or not str(tags).strip() or str(tags).strip() == "unknown"
        )
        status_missing = completion_status is None or not str(completion_status).strip()
        if tag_missing and task_date < today:
            unknown_tags.append(
                {
                    "id": todo_id,
                    "time_slot": time_slot,
                    "task": task,
                    "tags": tags or "unknown",
                },
            )

        if status_missing:
            include_status = task_date < today
            if task_date == today and time_slot:
                try:
                    _, end_str = [t.strip() for t in time_slot.split("-")]
                    end_time = datetime.strptime(end_str, "%H:%M").time()
                    end_dt = now.replace(
                        hour=end_time.hour,
                        minute=end_time.minute,
                        second=0,
                        microsecond=0,
                    )
                    include_status = now >= end_dt
                except (ValueError, AttributeError):
                    include_status = False
            if include_status:
                unknown_status.append(
                    {
                        "id": todo_id,
                        "time_slot": time_slot,
                        "task": task,
                    },
                )

    return jsonify(
        {
            "success": True,
            "unknown_tags": unknown_tags,
            "unknown_status": unknown_status,
        },
    )


@todo_bp.post("/todo/update_tag")
@login_required
def update_tag():
    """Update task tags for a specific todo item."""
    user = get_current_username()
    if user is None:
        return jsonify({"success": False, "error": "not logged in"}), 401

    data = request.get_json() or {}
    todo_id = data.get("id")
    tag = (data.get("tag") or "").strip().lower()
    if not todo_id or not tag:
        return jsonify({"success": False, "error": "missing data"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT username FROM todo_list WHERE id = %s", (todo_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": "not found"}), 404

    task_owner = row[0]
    if user.role != "admin" and task_owner != user.username:
        cur.close()
        conn.close()
        return jsonify({"success": False, "error": "forbidden"}), 403

    cur.execute("UPDATE todo_list SET tags = %s WHERE id = %s", (tag, todo_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True})


@todo_bp.route("/exec_rules/<string:selected_user_id>", methods=["POST"])
@login_required
def exec_rules(selected_user_id: str):
    """Execute assigned rules for the selected user."""
    if not RULE_EXEC_LOCK.acquire(blocking=False):
        flash("Rules update already in progress.", "warning")
        return redirect(url_for("todo.todo_page"))
    now = time_module.monotonic()
    remaining = RULE_EXEC_COOLDOWN_SECONDS - (now - RULE_EXEC_STATE["last_run"])
    if remaining > 0:
        RULE_EXEC_LOCK.release()
        flash(f"Please wait {remaining:.0f}s before trying again.", "warning")
        return redirect(url_for("todo.todo_page"))
    RULE_EXEC_STATE["last_run"] = now
    user_id = selected_user_id
    conn = get_db_connection()
    cur = conn.cursor()
    try:
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
            notify_schedule_change()
    finally:
        conn.close()
        RULE_EXEC_LOCK.release()
    return redirect(url_for("todo.todo_page"))
