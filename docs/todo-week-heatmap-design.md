# Design — This-Week Strip & 12-Week Activity Heatmap (todo page)

Fills the two placeholders in `src/safe_family/templates/todo/todo.html`:
the **this-week strip** (currently dashes) and the **activity heatmap
reserved card** (`.sf-heatmap-reserve`).

## Key decision: no database schema change

`todo_list` already retains full per-date history — the daily save in
`todo_page()` only deletes/rewrites *today's* rows, and the nightly
`archive_completed_tasks` job only touches `long_term_goals`, never
`todo_list`. Every column needed already exists: `username`, `date`,
`time_slot`, `completed`, `completion_status`.

Only DB change (optional, recommended): an index in `scripts/migrate.py`:

```sql
CREATE INDEX IF NOT EXISTS idx_todo_list_username_date
    ON todo_list (username, date);
```

## 1. Shared metric: subject-weighted daily completion %

Both widgets show the same number per day:

```
day_pct = min(200, round(100 × Σ(slot_minutes × status_w  over mandatory tasks)
                             / DAILY_TARGET_MINUTES))
```

The score measures **absolute time spent on mandatory subjects** (math,
science, language, piano — `MANDATORY_SUBJECTS`), not the share of the
day's own plan. A light day can't score high without real work, and days
are comparable to each other. `DAILY_TARGET_MINUTES = 120` defines 100%
(two focused hours); the scale caps at 200%. Non-mandatory tasks appear
in the hover details but earn nothing. Unparseable time slots assume
`DEFAULT_SLOT_MINUTES` (60).

- **status_w** — existing `STATUS_WEIGHTS` from
  `src/safe_family/cli/weekly_metrics.py` (skipped 0.0 · partially 0.25 ·
  half 0.5 · mostly 0.75 · done 1.0). If `completion_status` is empty,
  fall back to `1.0 if completed else 0.0` — covers today, where the kid
  checks boxes before the feedback modal assigns a status.
- **subject_w** — mandatory subjects weigh more:

  ```python
  # todo.py — single source of truth
  MANDATORY_SUBJECTS = {"math", "science", "piano"}
  MANDATORY_WEIGHT = 2.0   # everything else = 1.0
  ```

  Subject is `task.split('[')[0].strip().lower()` — the same parse the
  template uses for its `is_mandatory` badge, so the "Mandatory" tag and
  the extra weight can never disagree.
- **slot_minutes** — parsed with the existing
  `weekly_metrics._parse_time_slot_minutes()`; if unparseable, fall back
  to 1.0 per task (count-based).
- A date with **no rows at all** → `None` ("no plan"), rendered
  differently from 0% ("planned but skipped").

Worked example, four 60-min slots:

| Task    | Mandatory | Status          | Earned minutes |
|---------|-----------|-----------------|----------------|
| math    | yes       | done (1.0)      | 60             |
| piano   | yes       | half done (0.5) | 30             |
| books   | no        | done (1.0)      | 0              |
| leasure | no        | skipped (0.0)   | 0              |

`day_pct = 90 / 120 = 75%`. Four fully-done mandatory hours reach the
200% cap.

**Weekly summary stays untouched.** `weekly_metrics.py` keeps its
unweighted formula; the subject weighting lives only in the new
`daily_completion_map()` helper feeding the strip and heatmap. Past
history is re-scored on the fly under the weighted formula (heatmap is
computed per request, nothing is stored).

## 2. Data flow — server-side, no new endpoint

Everything is computed inside `todo_page()` with one query covering 84
days (12 ISO weeks ending with the current week); the current week is
sliced out of the same result for the strip.

New helper in `src/safe_family/todo/todo.py`:

```python
def daily_completion_map(cur, username, start_date, end_date) -> dict[date, int | None]:
    """One query over todo_list; {date: pct or None} for every day in range."""
```

Two new template variables:

```python
week_strip: list[dict]   # 7 items, Monday → Sunday of the current ISO week
    # {"label": "M", "date": "2026-06-29", "pct": 83 | None,
    #  "is_today": bool, "is_future": bool}

heatmap: dict
    # {"start": "2026-04-13",            # Monday, 11 weeks before current week
    #  "weeks": [[pct|None] × 7] × 12,   # weeks[w][d], d=0 is Monday
    #  "month_labels": [{"col": 0, "text": "Apr"}, ...]}
```

Why not a JSON endpoint + fetch: the page already reloads on every admin
player-switch and every save, the route already holds an open cursor, and
84 days × ~10 slots is a trivial query. If the mobile app later needs
this, extract the helper into a `GET /todo/history` endpoint.

## 3. This-week strip (`.sf-week-strip`)

- Each `.sf-week-day .v` cell gets a bottom-anchored fill bar
  (`height: pct%`, capped at 100) using the shade scale in §5, plus the
  `.pct` label. Hover shows task details only (no percentage), like the
  heatmap.
- `pct is None` (past/today) → em-dash on `var(--sf-surface-3)`.
- `is_future` → empty cell, no label, `opacity: .45`.
- `is_today` → accent border + soft glow, matching the rainbow "now"
  marker language.
- Week starts Monday (ISO), labels `M T W T F S S`.
- The "will appear here once weekly summary data is wired in" note is
  removed.

## 4. Activity heatmap (`.sf-heatmap-reserve` → `.sf-heatmap`)

Pure Jinja + CSS grid, no canvas, no JS:

- Grid: `repeat(7, 12px)` rows, `grid-auto-flow: column`, 12px columns,
  3px gap. Rows Mon→Sun top-to-bottom, columns oldest→newest
  left-to-right (GitHub-style); newest column = current week.
- Card keeps `.sf-card` styling (dashed border → solid); the grid sits in
  an `overflow-x: auto` wrapper.
- Row labels `M W F` left, month labels above the first column of each
  month, legend `less ▢▢▢▢▢ more` right.
- Cell tooltip: native multiline `title` with the date plus one
  `task · completion_status` line per slot (or `2026-06-29 · no plan`).
  The percentage is deliberately **not** shown to the kid — hover reveals
  what was planned and how each task went, nothing else. Same tooltip on
  the week-strip cells.
- Future days of current week: transparent cells (rectangle preserved).

## 5. Orange shade scale (shared)

Uses accent tokens via `color-mix` so light/dark themes both work; no
hardcoded hex. Implemented as `data-level` attribute selectors; the level
is computed by a shared Jinja macro.

| Level  | Condition     | Fill |
|--------|---------------|------|
| none   | pct is None   | `var(--sf-surface-3)` + `1px solid var(--sf-border)` |
| 0      | pct = 0       | `var(--sf-danger-soft)` |
| 1      | 1–34          | `color-mix(in srgb, var(--sf-accent) 25%, var(--sf-surface-3))` |
| 2      | 35–64         | `color-mix(in srgb, var(--sf-accent) 50%, var(--sf-surface-3))` |
| 3      | 65–89         | `color-mix(in srgb, var(--sf-accent) 80%, var(--sf-surface-3))` |
| 4      | 90–100        | `linear-gradient(135deg, var(--sf-accent), var(--sf-accent-glow))` |
| 5      | 101–150       | level-4 gradient + `box-shadow: 0 0 6px var(--sf-accent-soft)` |
| 6      | 151–200       | glow gradient + `box-shadow: 0 0 8px var(--sf-accent-glow)` |

Levels 5–6 mark "extra credit": more mandatory-weighted work than a plain
full day. The week-strip fill bar caps its height at 100% but the label
shows the real value (e.g. `160%`).

## 6. Edge cases

- Admin viewing another player: both widgets follow `selected_user`.
- Timezone: all date math uses `datetime.now(local_tz).date()`.
- Split slots produce two 30-min rows; minutes-weighting handles them
  with no special casing.
- Empty history: strip shows 7 dashes, heatmap shows 84 "no plan" cells.

## 7. Files touched & tests

| File | Change |
|------|--------|
| `src/safe_family/todo/todo.py` | constants + `daily_completion_map()`; wire into `todo_page()` |
| `src/safe_family/templates/todo/todo.html` | strip loop, heatmap card, scale CSS + macro |
| `scripts/migrate.py` | `(username, date)` index |
| `tests/test_todo.py` | unit tests: mixed statuses, empty-status fallback, unparseable slot fallback, no rows → None, bucket boundaries (0, 34/35, 89/90), mandatory weighting |

Coverage gate: touched module stays ≥ 80% (`pytest -q`).
