# Coverage Improvement Plan (Target 80%)

## Current status
- Coverage now meets the 80% gate (last run: 81.6% with branch coverage enabled).
- Biggest gaps remain in large modules (auth, scheduler, blocker).
- Goal: keep coverage >= 80% while closing remaining branch/error-path gaps.

## High-impact modules (priority order)
File | Statements | Current cover | Why it matters
--- | --- | --- | ---
src/safe_family/todo/todo.py | 462 | 79% | Core UI and notifications (improved from 9%)
src/safe_family/core/auth.py | 403 | 76% | Auth, JWT, session, OAuth, notesync codes
src/safe_family/rules/scheduler.py | 363 | 73% | Background jobs and advisory locks
src/safe_family/urls/blocker.py | 129 | 61% | AdGuard and router rule toggles
src/safe_family/urls/analyzer.py | 87 | 75% | Log parsing and analysis
src/safe_family/api/routes.py | 106 | 77% | Notesync API + notes list
src/safe_family/todo/goals.py | 115 | 92% | Separated long-term goals logic (New)
src/safe_family/urls/notes.py | 68 | 86% | UI for notes viewer (pagination/media)

Secondary modules close to 80 or above:
- src/safe_family/core/models.py (93%)
- src/safe_family/notesync/schemas.py (96%)
- src/safe_family/app.py (95%)
- src/safe_family/notifications/notifier.py (82%)

## Test cases to add (by feature)
Legend: [x] done, [ ] pending.

### Notesync service and API
- [x] LWW comparisons for upsert (incoming older vs newer)
- [x] Delete recency uses max(updatedAt, deletedAt)
- [x] Skip when existing is newer, apply when incoming is newer
- [x] Duplicate op handling (same opId twice returns skipped)
- [ ] Tags: normalize whitespace and drop blanks
- [x] Tags: drop duplicates and preserve case
- [ ] Tags: replace existing tags on update
- [x] Media: decode and store new media
- [x] Media: update existing media when checksum changes
- [x] Media: skip duplicate checksum on same note
- [x] Media: invalid base64 returns error
- [ ] API routes: invalid JSON payload (raw bytes)
- [x] API routes: validation errors
- [x] API routes: missing/invalid API key and JWT
- [x] API routes: notesync success response shape
- [x] API routes: GET /api/notes limit parsing and deleted filtering

Suggested files to extend:
- tests/test_notesync_lww.py
- tests/test_notesync_media_tags.py
- tests/test_notesync_auth.py
- tests/test_auth_exchange.py
- tests/test_api_notes.py

### Auth and session routes
- [x] Register/login success and failure paths
- [x] Refresh and logout (blocklist write)
- [x] Whoami returns claims
- [ ] Whoami requires JWT (missing token path)
- [x] require_api_key decorator returns 401 when missing/wrong
- [ ] OAuth callback state mismatch
- [ ] OAuth callback missing code
- [x] OAuth callback success redirect to app (iOS)
- [x] OAuth callback success sets session (web)
- [x] Auth code exchange success
- [x] Auth code exchange invalid code
- [x] Auth code exchange reuse
- [ ] Auth code exchange expired code

Suggested files to extend:
- tests/test_auth.py
- tests/test_auth_routes.py
- tests/test_auth_exchange.py

### Todo planner & Goals
- [x] generate_time_slots weekday vs weekend
- [ ] generate_time_slots holiday mode
- [x] generate_time_slots custom valid
- [x] generate_time_slots invalid custom range fallback
- [x] generate_time_slots 30 vs 60 minute slots
- [x] todo_page admin vs user views
- [x] todo_page saves tasks and sends notifications
- [ ] todo_page missing user redirects
- [x] update_todo updates tasks and sends notifications
- [x] done_todo updates status
- [ ] done_todo auto-complete after end time
- [x] mark_status invalid + success paths
- [x] notify_feedback/notify_current_task routes
- [x] split_slot success + forbidden paths
- [x] long-term goal create/update/reorder/start/stop/delete/update due (in goals.py)
- [x] update_tag success + forbidden paths
- [x] unknown_metadata filtering
- [x] goals page renders and admin user switching

Suggested files to extend:
- tests/test_todo.py
- tests/test_units.py
- tests/test_goals_route.py

### Scheduler and automation
- [x] _ensure_scheduler_leader returns False when lock not acquired
- [x] _ensure_job_lock returns False when lock held
- [x] _wrap_job returns _JOB_SKIPPED when not leader
- [x] schedule change notification calls pg_notify
- [x] _log_job_event handles exceptions and skipped jobs
- [x] schedule_rules add/update/assign actions
- [ ] load_schedules handles empty schedule list
- [ ] listener path coverage for schedule change notifications

Suggested files to extend:
- tests/test_scheduler.py

### URL log pipeline
- [x] receiver invalid JSON returns 400
- [x] receiver valid payload inserts row
- [x] receiver DB errors return 500
- [x] get_time_range valid and invalid cases
- [x] log_analysis inserts expected rows
- [ ] log_analysis delete paths
- [x] suspicious list view and date filter
- [ ] suspicious pagination/search edge cases
- [x] add/remove/modify block list and filter rules

Suggested files to extend:
- tests/test_receiver.py
- tests/test_analyzer.py
- tests/test_suspicious.py

### Blocking rules (AdGuard, router)
- [x] _post_filter_rule and _update_blocked_services payloads
- [x] rule_enable/disable functions hit correct endpoints
- [x] cooldown behavior in disable AI flow
- [ ] error handling for request timeouts

Suggested files to extend:
- tests/test_blocker.py

### Notifications
- [x] email notification formats and recipients
- [x] Discord notification payloads and empty webhook behavior
- [x] Hammerspoon alert/task only sends when server reachable

Suggested files to extend:
- tests/test_notifier.py

### Auto Git exports
- [x] rule_auto_commit writes rule files and runs git commands
- [x] auto_import reads block files and inserts rows
- [ ] error handling when git commands fail

Suggested files to extend:
- tests/test_auto_git.py

### CLI tools and reports
- [ ] analyze: invalid args, custom ranges
- [x] weekly_diff output formatting
- [x] weekly_diff missing files
- [x] weekly_metrics no data vs data
- [x] weekly_metrics output file/dir paths
- [x] weekly_metrics DB query path
- [ ] gentags: empty or malformed input

Suggested files to extend:
- tests/test_cli_analyze.py
- tests/test_cli_reports.py

### Misc routes and users
- [x] notes view requires login
- [x] notes media endpoint 404 when missing
- [x] notes media endpoint 404 when not owned (private notes)
- [x] notes media endpoint success when owned or public
- [x] notes view pagination logic
- [x] notes media M4A mimetype correction
- [x] users list and serialization basics

Suggested files to extend:
- tests/test_routes.py
- tests/test_users.py
- tests/test_misc_routes.py

## Fixtures and mocks to reuse
- tests/conftest.py provides:
  - FakeConnection/FakeCursor for raw SQL
  - notesync_app/notesync_client for SQLAlchemy notesync tests
  - patch_requests for network calls
  - patch_mail for email sends
- Prefer monkeypatching external services (requests, subprocess, socket)
- Keep DB writes inside sqlite or FakeConnection unless a real Postgres fixture is required

## Verification
- Run `pytest` (coverage config is in `pyproject.toml`)
- Watch per-module coverage to confirm the high-impact files trend toward 80