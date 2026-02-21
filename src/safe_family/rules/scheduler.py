"""Scheduler for automated rule execution."""

import atexit
import logging
import os
import select
import threading
import time
import uuid
import zlib
from datetime import datetime, timedelta

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Blueprint, flash, redirect, render_template, request, url_for

from src.safe_family.auto_git.auto_git import rule_auto_commit
from src.safe_family.core.auth import admin_required
from src.safe_family.core.extensions import get_db_connection, local_tz
from src.safe_family.notifications.notifier import send_hammerspoon_alert
from src.safe_family.urls.analyzer import (
    get_time_range,
    log_analysis,
)
from src.safe_family.urls.blocker import (
    rule_allow_traffic_all,
    rule_disable_ai,
    rule_disable_all,
    rule_enable_ai,
    rule_enable_all_except_ai,
    rule_stop_traffic_all,
)
from src.safe_family.urls.receiver import run_adguard_pull
from src.safe_family.utils.constants import DAYS_IN_WEEK

logger = logging.getLogger(__name__)
schedule_rules_bp = Blueprint("schedule_rules", __name__, template_folder="templates")


# Example mapping of rule names to Python functions
def run_rule_a():
    """Test Run Rule A."""
    logger.info("hello A at %s", str(datetime.now(local_tz)))


def run_rule_b():
    """Test Run Rule B."""
    logger.info("hello B at %s", str(datetime.now(local_tz)))


RULE_FUNCTIONS = {
    "Rule enable all except AI": rule_enable_all_except_ai,
    "Rule disable all": rule_disable_all,
    "Rule enable AI": rule_enable_ai,
    "Rule disable AI": rule_disable_ai,
    "Rule stop traffic all": rule_stop_traffic_all,
    "Rule allow traffic all": rule_allow_traffic_all,
    "Rule auto commit": rule_auto_commit,
}


SCHEDULE_CHANGE_CHANNEL = "schedule_rules_changed"
_SCHEDULER_INSTANCE_ID = uuid.uuid4().hex
_LOAD_SCHEDULES_LOCK = threading.Lock()
_JOB_LOCKS: dict[str, object] = {}
_JOB_LOCKS_LOCK = threading.Lock()
_LISTENER_THREAD: threading.Thread | None = None
_LISTENER_LOCK = threading.Lock()
_LISTENER_STOP = threading.Event()
_SCHEDULER_LEADER_LOCK_KEY = zlib.crc32(b"safe_family_scheduler_leader")
_SCHEDULER_LEADER_CONN = None
_SCHEDULER_LEADER_LOCK = threading.Lock()
_IS_SCHEDULER_LEADER = False
_JOB_SKIPPED = object()


def _job_lock_key(job_id: str) -> int:
    """Return a stable advisory lock key for a job ID."""
    return zlib.crc32(job_id.encode("utf-8"))


def _ensure_scheduler_leader() -> bool:
    """Return True if this process is the scheduler leader."""
    global _IS_SCHEDULER_LEADER, _SCHEDULER_LEADER_CONN
    with _SCHEDULER_LEADER_LOCK:
        if _IS_SCHEDULER_LEADER and _SCHEDULER_LEADER_CONN is not None:
            try:
                cur = _SCHEDULER_LEADER_CONN.cursor()
                cur.execute("SELECT 1")
                cur.close()
                return True
            except Exception:
                logger.warning("Scheduler leader connection lost; re-electing.")
                try:
                    _SCHEDULER_LEADER_CONN.close()
                except Exception:
                    logger.exception("Failed to close leader connection.")
                _SCHEDULER_LEADER_CONN = None
                _IS_SCHEDULER_LEADER = False

        conn = None
        try:
            conn = get_db_connection()
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(
                "SELECT pg_try_advisory_lock(%s)",
                (_SCHEDULER_LEADER_LOCK_KEY,),
            )
            locked = cur.fetchone()[0]
            cur.close()
        except Exception:
            logger.exception("Failed to acquire scheduler leader lock.")
            if conn is not None:
                conn.close()
            return False

        if not locked:
            conn.close()
            return False

        _SCHEDULER_LEADER_CONN = conn
        _IS_SCHEDULER_LEADER = True
        return True


def _release_scheduler_leader() -> None:
    """Close the scheduler leader connection."""
    global _IS_SCHEDULER_LEADER, _SCHEDULER_LEADER_CONN
    with _SCHEDULER_LEADER_LOCK:
        if _SCHEDULER_LEADER_CONN is not None:
            try:
                _SCHEDULER_LEADER_CONN.close()
            except Exception:
                logger.exception("Failed to close scheduler leader connection.")
        _SCHEDULER_LEADER_CONN = None
        _IS_SCHEDULER_LEADER = False


def _ensure_job_lock(job_id: str) -> bool:
    """Return True if this process owns the advisory lock for a job."""
    with _JOB_LOCKS_LOCK:
        conn = _JOB_LOCKS.get(job_id)
        if conn is not None and conn.closed == 0:
            return True

    lock_key = _job_lock_key(job_id)
    conn = None
    try:
        conn = get_db_connection()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
        locked = cur.fetchone()[0]
        cur.close()
    except Exception:
        logger.exception("Failed to acquire job lock for %s", job_id)
        if conn is not None:
            conn.close()
        return False

    if not locked:
        conn.close()
        return False

    with _JOB_LOCKS_LOCK:
        _JOB_LOCKS[job_id] = conn
    return True


def _wrap_job(job_id: str, func):
    """Wrap a scheduled function with a per-job advisory lock."""

    def _wrapped(*args, **kwargs):
        if not _ensure_scheduler_leader():
            return _JOB_SKIPPED
        if not _ensure_job_lock(job_id):
            logger.debug("Skipping job %s; lock held by another process.", job_id)
            return _JOB_SKIPPED
        return func(*args, **kwargs)

    return _wrapped


def _release_unused_job_locks(active_job_ids: set[str]) -> None:
    """Close advisory lock connections for jobs that are no longer scheduled."""
    with _JOB_LOCKS_LOCK:
        for job_id in list(_JOB_LOCKS.keys()):
            if job_id in active_job_ids:
                continue
            conn = _JOB_LOCKS.pop(job_id)
            try:
                if conn is not None and conn.closed == 0:
                    conn.close()
            except Exception:
                logger.exception("Failed to release job lock for %s", job_id)


def _listen_once() -> None:
    """Listen for schedule change notifications and reload jobs.

    Three empty lists ([], [], []), it means the 1-second timeout finished and nothing happened (no notifications arrived)
    """
    conn = get_db_connection()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"LISTEN {SCHEDULE_CHANGE_CHANNEL}")

    try:
        while not _LISTENER_STOP.is_set():
            if select.select([conn], [], [], 1.0) == ([], [], []):
                continue
            conn.poll()
            while conn.notifies:
                notify = conn.notifies.pop(0)
                if notify.payload == _SCHEDULER_INSTANCE_ID:
                    continue
                logger.info("Reloading schedules after notification.")
                load_schedules()
    finally:
        cur.close()
        conn.close()


def _listen_for_schedule_changes() -> None:
    while not _LISTENER_STOP.is_set():
        try:
            _listen_once()
        except Exception:
            logger.exception("Listener crashed, retrying in 5s")
            time.sleep(5)


def _start_schedule_listener() -> None:
    """Start a background listener for schedule change notifications."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    global _LISTENER_THREAD
    with _LISTENER_LOCK:
        if _LISTENER_THREAD is not None:
            return
        _LISTENER_THREAD = threading.Thread(
            target=_listen_for_schedule_changes,
            name="schedule-change-listener",
            daemon=True,
        )
        _LISTENER_THREAD.start()


def _stop_schedule_listener() -> None:
    """Signal the schedule listener thread to stop."""
    _LISTENER_STOP.set()


atexit.register(_stop_schedule_listener)
atexit.register(_release_scheduler_leader)


def notify_schedule_change() -> None:
    """Notify other processes to reload schedules."""
    try:
        conn = get_db_connection()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            "SELECT pg_notify(%s, %s)",
            (SCHEDULE_CHANGE_CHANNEL, _SCHEDULER_INSTANCE_ID),
        )
        cur.close()
        conn.close()
    except Exception:
        logger.exception("Failed to notify schedule change.")


def _log_job_event(event) -> None:
    """Log a single line per job run to avoid APScheduler's duplicate INFO logs."""
    if event.exception:
        logger.error("Scheduler job %s failed: %s", event.job_id, event.exception)
        return
    if getattr(event, "retval", None) is _JOB_SKIPPED:
        return
    logger.info("Scheduler job %s executed", event.job_id)


# 0-6 → Sunday to Saturday (APScheduler uses 0=Monday, 6=Sunday).
scheduler = BackgroundScheduler(timezone=local_tz)
scheduler.add_listener(_log_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
scheduler.start()
_start_schedule_listener()
_NOTIFIED_TASK_IDS: set[int] = set()
_NOTIFIED_DATE: str | None = None


def get_scheduled_job_details():
    """Return a human-friendly view of the current scheduler jobs."""
    jobs = []
    for job in scheduler.get_jobs():
        next_run_time = job.next_run_time
        if next_run_time:
            try:
                next_run_time = next_run_time.astimezone(local_tz)
            except Exception:
                logger.exception("  Next Run Time: %s", job["next_run_time"])
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "trigger": str(job.trigger),
                "next_run_time": (
                    next_run_time.strftime("%Y-%m-%d %H:%M:%S %Z")
                    if next_run_time
                    else "-"
                ),
            },
        )
    return jobs


def load_schedules():
    """Clear existing jobs and reload from DB."""
    with _LOAD_SCHEDULES_LOCK:
        scheduler.remove_all_jobs()
        active_job_ids: set[str] = set()

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, rule_name, start_time, day_of_week FROM schedule_rules WHERE enabled = TRUE",
        )
        for rule_id, rule_name, start_time, day_of_week in cur.fetchall():
            if rule_name in RULE_FUNCTIONS:
                func = RULE_FUNCTIONS.get(rule_name)
                if func:
                    job_id = f"rule_{rule_id}"
                    active_job_ids.add(job_id)
                    scheduler.add_job(
                        _wrap_job(job_id, func),
                        "cron",
                        id=job_id,  # important: job ID tied to DB row
                        name=rule_name,
                        hour=start_time.hour,
                        minute=start_time.minute,
                        day_of_week=day_of_week or "*",
                    )
        cur.close()
        conn.close()

        # Still prefer "cron" compare to ("interval", hours=24)
        scheduler.add_job(
            _wrap_job("archive_completed_tasks", archive_completed_tasks),
            "cron",
            id="archive_completed_tasks",
            name="archive_completed_tasks",
            hour=2,
            minute=10,
            day_of_week="*",
        )
        active_job_ids.add("archive_completed_tasks")
        scheduler.add_job(
            _wrap_job("analyze_logs", analyze_logs),
            "cron",
            id="analyze_logs",
            name="analyze_logs",
            hour=0,
            minute=20,
            day_of_week="*",
        )
        active_job_ids.add("analyze_logs")
        scheduler.add_job(
            _wrap_job("notify_overdue_task_feedback", notify_overdue_task_feedback),
            "interval",
            minutes=1,
            id="notify_overdue_task_feedback",
            name="notify_overdue_task_feedback",
            replace_existing=True,
        )
        active_job_ids.add("run_adguard_pull")
        scheduler.add_job(
            _wrap_job("run_adguard_pull", run_adguard_pull),
            "interval",
            minutes=3,
            id="run_adguard_pull",
            name="run_adguard_pull",
            replace_existing=True,
        )
        active_job_ids.add("run_adguard_pull")

        _release_unused_job_locks(active_job_ids)

        # Get all scheduled jobs
        jobs = get_scheduled_job_details()

        # Iterate through the jobs and log their details
        logger.info("-" * 20)
        logger.info("Scheduled Jobs:")
        for job in jobs:
            logger.info("  ID:  %s", job["id"])
            logger.info("  Name: %s", job["name"])
            logger.info("  Trigger: %s", job["trigger"])
            logger.info("  Next Run Time: %s", job["next_run_time"])
            logger.info("-" * 20)


def remove_job(rule_id: int):
    """Remove a job when a rule is deleted."""
    job_id = f"rule_{rule_id}"
    try:
        scheduler.remove_job(job_id)
        logger.debug("Removed job %s", job_id)
    except Exception as e:
        logger.debug("Job %s not found: %s", job_id, str(e))


def notify_overdue_task_feedback():
    """Send a desktop alert when task feedback is overdue."""
    global _NOTIFIED_DATE
    today = datetime.now(local_tz).date().isoformat()
    if today != _NOTIFIED_DATE:
        _NOTIFIED_DATE = today
        _NOTIFIED_TASK_IDS.clear()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, username, time_slot, task
        FROM todo_list
        WHERE date = CURRENT_DATE
          AND COALESCE(completion_status, '') = ''
        """,
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    now = datetime.now(local_tz)
    for todo_id, username, time_slot, task in rows:
        if todo_id in _NOTIFIED_TASK_IDS:
            continue
        try:
            _, end_str = [t.strip() for t in time_slot.split("-")]
            end_time = datetime.strptime(end_str, "%H:%M").time()
        except (ValueError, AttributeError):
            continue

        end_dt = now.replace(
            hour=end_time.hour,
            minute=end_time.minute,
            second=0,
            microsecond=0,
        )
        if now < end_dt:
            continue

        if time_slot and task:
            message = f"{time_slot} - {task}"
        else:
            message = time_slot or task or username

        send_hammerspoon_alert(message)
        _NOTIFIED_TASK_IDS.add(todo_id)


@schedule_rules_bp.route("/schedule_rules", methods=["GET", "POST"])
@admin_required
def schedule_rules():
    """View and manage scheduled rules."""
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "update":
            rule_id = request.form["rule_id"]
            start_time = request.form["start_time"] or None
            end_time = request.form["end_time"] or None
            selected_days = request.form.getlist("day_of_week")
            if not selected_days or len(selected_days) == DAYS_IN_WEEK:
                day_of_week = "*"  # all days
            else:
                day_of_week = ",".join(selected_days)
            cur.execute(
                "UPDATE schedule_rules SET start_time = %s, end_time = %s, day_of_week = %s WHERE id = %s",
                (start_time, end_time, day_of_week, rule_id),
            )
            conn.commit()
            load_schedules()
            notify_schedule_change()

        elif action == "add":
            rule_name = request.form["rule_name"]
            start_time = request.form["start_time"] or None
            end_time = request.form["end_time"] or None

            cur.execute(
                """
                INSERT INTO schedule_rules (rule_name, start_time, end_time, enabled)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (rule_name, start_time, end_time, True),
            )
            new_rule = cur.fetchone()
            if new_rule:  # always check
                rule_id = new_rule[0]
                logger.debug("Inserted rule with id: %d", rule_id)
            conn.commit()
            load_schedules()
            notify_schedule_change()

        elif action == "delete":
            rule_id = request.form["rule_id"]
            remove_job(rule_id)
            cur.execute("DELETE FROM schedule_rules WHERE id = %s", (rule_id,))
            conn.commit()
            load_schedules()
            notify_schedule_change()

        elif action == "enable":
            rule_id = request.form["rule_id"]
            cur.execute(
                "UPDATE schedule_rules SET enabled = TRUE WHERE id = %s",
                (rule_id,),
            )
            conn.commit()
            load_schedules()
            notify_schedule_change()

        elif action == "disable":
            rule_id = request.form["rule_id"]
            cur.execute(
                "UPDATE schedule_rules SET enabled = FALSE WHERE id = %s",
                (rule_id,),
            )
            conn.commit()
            load_schedules()
            notify_schedule_change()

        elif action == "assign":
            for key, value in request.form.items():
                print("Processing:", key, value)
                if key.startswith("rule_"):
                    uid = key.split("_")[1]
                    cur.execute(
                        """
                        INSERT INTO user_rule_assignment (user_id, assigned_rule)
                        VALUES (%s, %s)
                        ON CONFLICT (user_id)
                        DO UPDATE SET assigned_rule = EXCLUDED.assigned_rule
                    """,
                        (uid, value),
                    )
            conn.commit()
            flash("Rule assignments updated.", "success")

        return redirect(url_for("schedule_rules.schedule_rules"))

    cur.execute("""
        SELECT u.id AS user_id, u.username, a.assigned_rule
        FROM users u
        LEFT JOIN user_rule_assignment a
        ON u.id = a.user_id
        ORDER BY u.username;
    """)
    assigned_rules = cur.fetchall()
    cur.execute("""
        SELECT id, rule_name, start_time,
        end_time, day_of_week, enabled
        FROM schedule_rules
        ORDER BY enabled DESC, start_time ASC
    """)
    rules = cur.fetchall()
    cur.close()

    scheduled_jobs = get_scheduled_job_details()

    return render_template(
        "rules/schedule_rules.html",
        rules=rules,
        assigned_rules=assigned_rules,
        available_rules=RULE_FUNCTIONS.keys(),
        scheduled_jobs=scheduled_jobs,
    )


def archive_completed_tasks():
    """Move completed tasks to history table."""
    logger.info("Start archiving completed tasks...")
    conn = get_db_connection()
    cur = conn.cursor()
    cur_his = conn.cursor()

    three_days_ago = datetime.now(local_tz) - timedelta(days=3)

    # 1. Select tasks completed 3+ days ago
    cur.execute(
        """
        SELECT goal_id, user_id, task_text, priority, completed_at, time_spent
        FROM long_term_goals
        WHERE completed = TRUE AND completed_at < %s
    """,
        (three_days_ago,),
    )
    rows = cur.fetchall()

    if not rows:
        conn.close()
        return

    # 2. Insert them into history table
    for row in rows:
        try:
            goal_id, user_id, task_text, priority, completed_at, time_spent = row
            cur_his.execute(
                """
                INSERT INTO long_term_goals_his (goal_id, user_id, task_text, priority, completed_at, time_spent)
                VALUES (%s, %s, %s, %s, %s, %s)
            """,
                (
                    goal_id,
                    user_id,
                    task_text,
                    priority,
                    completed_at.strftime("%Y-%m-%d %H:%M:%S"),
                    time_spent,
                ),
            )
            logger.info("Archived task: %s", str(row))
            # 3. Remove from active table
            cur.execute(
                "DELETE FROM long_term_goals WHERE goal_id = %s",
                (goal_id,),
            )
            logger.info("Move goal_id %d to history", goal_id)
            conn.commit()
        except Exception as e:
            logger.info("move to history not success: %s", str(e))

    conn.close()


def analyze_logs():
    """Analyze logs."""
    now = datetime.now(local_tz)
    start_time, end_time = get_time_range(
        range="yesterday",
        custom=None,
        now=now,
    )
    log_analysis(start_time, end_time)
