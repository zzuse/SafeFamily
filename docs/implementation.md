# SafeFamily Implementation Plan

Goal: Maintain and extend the SafeFamily Flask application for parental controls, log analysis, and family task planning.

Architecture:
- Nginx -> Gunicorn -> Flask -> PostgreSQL
- External integrations: AdGuard Home API, router gateway, Discord webhook, SMTP email, Hammerspoon desktop alerts, Git

Tech Stack:
- Python 3.11, Flask, Flask-SQLAlchemy, Flask-JWT-Extended, psycopg2
- APScheduler, pandas
- Flask-Mail, requests
- Jinja2 templates, Tailwind CSS (build step), pytest

---

### Task 1: App factory, config, and extensions

Files:
- src/safe_family/app.py
- config/settings.py
- config/logging.py
- src/safe_family/core/extensions.py
- run.py

Steps:
1) Load settings from environment (dotenv) and map to Flask config.
2) Initialize logging and extensions (db, jwt, mail).
3) Register blueprints: root, receiver, analyzer, auto_git, rules_toggle, schedule_rules, suspicious, auth, users, todo.
4) Confirm local entrypoints (`run.py`, `flask --app src.safe_family.app run`).

Validation:
- `pytest tests/test_routes.py`
- `pytest tests/conftest.py`

---

### Task 2: Core models and database schema

Files:
- src/safe_family/core/models.py
- src/safe_family/core/schemas.py

Scope:
- SQLAlchemy models: User, TokenBlocklist, LongTermGoal
- Raw SQL tables used by features: logs, logs_daily, suspicious, block_list, filter_rule, schedule_rules, user_rule_assignment, todo_list, long_term_goals_his, block_types

Steps:
1) Keep model methods aligned with DB behavior (save/delete helpers).
2) Document or migrate raw SQL tables (scripts/migrate.py is a candidate hook).

Validation:
- `pytest tests/test_models.py`
- `pytest tests/test_users.py`

---

### Task 3: Authentication and authorization

Files:
- src/safe_family/core/auth.py
- src/safe_family/templates/auth/login.html
- src/safe_family/templates/auth/register.html

Scope:
- JWT API login/register/refresh/logout
- Session-based UI login with `login_required` and `admin_required`
- OAuth providers: GitHub and Google (env-driven)
- Token revocation storage via TokenBlocklist (JWT blocklist integration is still a TODO)

Validation:
- `pytest tests/test_auth.py`
- `pytest tests/test_routes.py`

---

### Task 4: Log ingestion and analysis pipeline

Files:
- src/safe_family/urls/receiver.py
- src/safe_family/urls/analyzer.py
- src/safe_family/cli/analyze.py
- scripts/log_poster.py

Scope:
- `POST /logs` ingests AdGuard log events into `logs`
- `log_analysis()` aggregates into `logs_daily` and derives `suspicious`
- CLI wrapper for scheduled or manual runs

Validation:
- `pytest tests/test_receiver.py`
- `pytest tests/test_analyzer.py`
- `pytest tests/test_cli_analyze.py`

---

### Task 5: Suspicious review and block list management

Files:
- src/safe_family/urls/suspicious.py
- src/safe_family/templates/rules/suspicious_view.html

Scope:
- Admin UI for suspicious URLs
- CRUD for `block_list` and `filter_rule`
- Pagination, search, and date filters

Validation:
- `pytest tests/test_suspicious.py`

---

### Task 6: Network blocking rules and router controls

Files:
- src/safe_family/urls/blocker.py

Scope:
- Toggle AdGuard rule lists and blocked service IDs
- Router gateway controls (enable/disable traffic)
- Cooldown and lock protection for repeated actions

Validation:
- `pytest tests/test_blocker.py`

---

### Task 7: Scheduler and automation

Files:
- src/safe_family/rules/scheduler.py

Scope:
- APScheduler jobs loaded from `schedule_rules`
- Leader election and advisory locks
- Daily jobs: archive completed tasks, analyze logs
- Realtime notifications: overdue task feedback

Validation:
- `pytest tests/test_scheduler.py`

---

### Task 8: Todo system and long-term goals

Files:
- src/safe_family/todo/todo.py
- src/safe_family/templates/todo/todo.html
- src/safe_family/static/js/todo.js

Scope:
- Daily time slot planning (weekday/holiday/custom)
- CRUD for tasks and completion status
- Split slots, tag updates, weekly summary, unknown metadata
- Long-term goals with tracking and reordering

Validation:
- `pytest tests/test_todo.py`
- `pytest tests/test_units.py`

---

### Task 9: Notifications and outbound messaging

Files:
- src/safe_family/notifications/notifier.py

Scope:
- Email via Flask-Mail
- Discord webhook updates
- Hammerspoon alerts and task notifications

Validation:
- `pytest tests/test_notifier.py`

---

### Task 10: Auto Git exports for block lists

Files:
- src/safe_family/auto_git/auto_git.py

Scope:
- Export block lists and filter rules to files
- Auto commit/push to the rule repository

Validation:
- `pytest tests/test_auto_git.py`

---

### Task 11: Deployment and documentation

Files:
- INSTALL.md
- docs/architecture.md
- docs/api.md
- docs/delployment.md
- deploy/

Scope:
- Gunicorn + Nginx config, systemd service, SSL
- Document API endpoints and expected payloads
- Record required environment variables and external dependencies

---

## Verification

- `pytest`
- `python run.py`
- `python -m safe_family.cli.analyze --range last_5min`
