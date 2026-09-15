# SafeFamily

SafeFamily is a personal family dashboard and parental control backend that
combines URL monitoring, rule automation, and planning tools with a lightweight
notesync API. It started as a safer-browsing tool and grew into a daily planner
and notes system.

This repo is opinionated and assumes integrations like AdGuard Home and a router
gateway. It is usable as a reference implementation even if you replace those
integrations.

## Highlights
- URL log ingestion and analysis to surface suspicious domains.
- Admin UI to review suspicious entries and manage block lists and filter rules.
- Rule toggles for AdGuard and router traffic control with cooldown safeguards.
- Scheduler with APScheduler plus Postgres advisory locks for safe multi-process jobs.
- Notesync API with LWW conflict handling, tags, and media attachments.
- Todo planner with time slots and a completion heatmap.
- Notifications via email, Discord webhooks, and local Hammerspoon alerts.
- Auto Git export/import for block list rules.

## Architecture
- Nginx -> Gunicorn -> Flask -> PostgreSQL
- Integrations: AdGuard Home API, router gateway, SMTP, Discord, Hammerspoon, Git

## Tech stack
- Python 3.11, Flask, Flask-SQLAlchemy, Flask-JWT-Extended
- APScheduler, pandas, psycopg2
- Jinja2 templates, hand-maintained plain CSS, pytest

## Project layout
- `src/safe_family/app.py` app factory and blueprint registration
- `src/safe_family/api/` notesync and auth exchange endpoints
- `src/safe_family/notesync/` sync service and schemas
- `src/safe_family/urls/` log receiver, analyzer, blocking, suspicious review
- `src/safe_family/todo/` planning UI and task management
- `src/safe_family/rules/` scheduler and rule automation
- `src/safe_family/notifications/` email, Discord, and desktop alerts
- `src/safe_family/auto_git/` rule export/import and auto-commit
- `scripts/` helper scripts and notesync schema
- `deploy/` gunicorn, nginx, systemd configs
- `docs/` API, architecture, and implementation notes

## Quickstart (local dev)
1) Create a virtualenv and install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

2) Configure environment variables (see Configuration).

3) Prepare the database:
- SQLAlchemy models expect tables for users and notes.
- Notesync tables are provided in `scripts/notesync_schema.sql`.
- Other features use raw SQL tables (logs, suspicious, block_list, schedule_rules,
  todo_list). See `docs/implementation.md` for the table list.

4) Run the app:
```bash
python run.py
```
or
```bash
flask --app src.safe_family.app run
```

## Dockerization

SafeFamily can be run as a multi-container application using Docker Compose.

### 1. Build and Run
Ensure you have a `.env` file configured (see [Configuration](#configuration)). Then run:
```bash
docker-compose up -d --build
```
This will start:
- **db**: PostgreSQL 15 (data persisted in `db_data` volume).
- **app**: Flask backend running on Gunicorn.
- **proxy**: Nginx acting as a reverse proxy (handles SSL/HTTP).

### 2. Database Initialization
On the first run, the `db` service automatically imports `deploy/init_db/dump.sql`.
After docker up, run `docker exec safefamily_app python scripts/migrate.py`.

### 3. Key Mounts and Overrides
- **Logs**: Backend logs are mirrored to the local `./logs` directory.
- **SSH Keys**: Local `~/.ssh` is mounted read-only to `/root/.ssh` in the `app` container to support Git operations.
- **AdGuard Rules**: The directory specified by `HOST_ADGUARD_RULE_PATH` in your `.env` is mounted to allow rule manipulation.

### 4. Useful Commands
- **Start / Stop (daily use)**: `docker compose start` / `docker compose stop`
- **View Logs**: `docker-compose logs -f app`
- **Restart App**: `docker-compose restart app`
- **Rebuild and Restart**: `docker-compose up -d --build app`
- **Run Migrations/CLI**:
  ```bash
  docker-compose exec app python -m safe_family.cli.analyze --range last_5min
  ```
- **Prune Cache** (safe — never touches volumes):
  ```bash
  docker builder prune -af    # build cache; regrows on every rebuild
  docker image prune -f       # dangling/untagged layers only
  sudo journalctl --vacuum-size=500M
  sudo systemctl restart systemd-journald
  ```
  Do **not** use `docker image prune -a` here: the `app` image is built locally
  and old builds are unrecoverable once pruned. To stop the journal regrowing,
  set `SystemMaxUse=500M` in `/etc/systemd/journald.conf`.

### 5. Database Persistence

The `db` service maps `db_data:/var/lib/postgresql/data`. This is a **named
volume**, not a bind mount, so the two halves mean different things:

- `/var/lib/postgresql/data` — PGDATA *inside the container*.
- `db_data` — a Docker-managed volume (declared under top-level `volumes:`),
  which Compose namespaces as `safefamily_db_data`.

Resolve the real host directory with:
```bash
docker volume inspect safefamily_db_data --format '{{.Mountpoint}}'
```

On this host Docker is installed via **snap**, so the data root is
`/var/snap/docker/common/var-lib-docker/...` rather than the usual
`/var/lib/docker/...`. Don't assume the path — always inspect it. Note that
`/var/lib/postgresql/14/main` (a native apt Postgres install) is unrelated to
this stack.

**Safe** — data survives all of these: `docker compose stop`/`start`,
`docker compose down` then `up`, container recreation, image rebuilds, and the
prune commands listed above.

**Destroys the database** — never run these against this stack:
```bash
docker compose down -v              # -v removes named volumes
docker volume rm safefamily_db_data
docker system prune --volumes
```

Because a named volume is less discoverable than a bind mount, take logical
backups rather than relying on the volume alone:
```bash
set -a; source .env; set +a    # else $DB_USER is empty and pg_dump fails
docker exec safefamily_db pg_dump -U "$DB_USER" "$DB_NAME" > backup_$(date +%F).sql
```
Restore with `psql -U "$DB_USER" -d "$DB_NAME" < backup.sql`. Skipping the
`source` step falls back to the compose defaults (`user`/`logdb`) and fails with
`role "user" does not exist`. If you would
rather have the data at a visible host path, switch line 13 of
`docker-compose.yml` to a bind mount and migrate the existing contents.

### 6. Host Maintenance Notes
- Snap auto-refreshes Docker several times a day (`snap refresh --time`). A
  refresh restarts the daemon and briefly stops containers; `restart: always`
  brings them back, but the timing is not under your control. Use
  `snap refresh --hold` or a maintenance window if that matters.
- Postgres publishes `5432` on all interfaces (`0.0.0.0`), not just localhost —
  intentional for remote pgAdmin, but it should be firewalled.

## Tests
Run the full suite with coverage enforcement:
```bash
pytest -q
```

Run a targeted test without coverage (useful for quick iterations):
```bash
pytest -q tests/test_misc_routes.py::test_notes_media_public_note_for_other_user --no-cov
```

Run with coverage but disable the fail-under gate:
```bash
pytest -q tests/test_misc_routes.py::test_notes_media_public_note_for_other_user --cov-fail-under=0
```

### CSS
`src/safe_family/static/css/styles.css` is hand-maintained plain CSS — edit it directly, no build step needed.

## Configuration
SafeFamily reads environment variables (dotenv supported).

Minimum for local development:
- `FLASK_SQLALCHEMY_DATABASE_URI`
- `FLASK_APP_SECRET_KEY`
- `FLASK_JWT_SECRET_KEY`
- `DB_PARAMS` (JSON string used by psycopg2, required by log, todo, and rules features)

Example `DB_PARAMS`:
```
{"dbname":"safefamily","user":"safefamily","password":"secret","host":"localhost","port":5432}
```

Notesync:
- `NOTESYNC_API_KEY`
- `NOTESYNC_AUTH_CODE_TTL_SECONDS`
- `NOTESYNC_MAX_REQUEST_BYTES`
- `NOTESYNC_CALLBACK_URL`

Integrations (optional, feature-specific):
- AdGuard Home: `ADGUARD_HOSTPORT`, `ADGUARD_USERNAME`, `ADGUARD_PASSWORD`,
  `ADGUARD_RULE_PATH`
- Router: `ROUTER_IP`
- Email: `MAIL_ACCOUNT`, `MAIL_PASSWORD`, `MAIL_PERSON_LIST`
- Discord: `DISCORD_WEBHOOK_URL`
- Hammerspoon: `HAMMERSPOON_ALERT_URL`
- OAuth: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`, `GOOGLE_CLIENT_PROJECT_ID`, `GOOGLE_CALLBACK_ROUTE`

## API
- Notesync endpoints live under `/api` and require `X-API-Key` + JWT.
- See `docs/api.md` for request/response examples.

## CLI and jobs
- `python -m safe_family.cli.analyze --range last_5min` runs log analysis.
- Scheduled rules are managed in the UI and executed by APScheduler
  (see `src/safe_family/rules/scheduler.py`).

## Deployment
- See `INSTALL.md` for full setup steps.
- Nginx/Gunicorn/systemd configs live in `deploy/`.
- Architecture overview: `docs/architecture.md`.

## License
MIT. See `LICENSE`.
