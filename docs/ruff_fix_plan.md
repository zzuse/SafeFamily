# Ruff cleanup plan

Snapshot taken 2026-07-12 with `ruff 0.15.20` and the repo's `pyproject.toml`
config (`lint.extend-select = ["ALL"]` with a small ignore list).

```bash
ruff check .          # 974 findings
```

| Location | Findings | Share |
|---|---|---|
| `tests/` | 764 | 78% |
| `src/safe_family/` | 185 | 19% |
| `scripts/` | 23 | 2% |
| `config/`, `deploy/` | 2 | <1% |

Only ~15 of the 974 point at real runtime-behavior risks. The rest is style
noise amplified by selecting `ALL`, most of it in test files. The plan below
works from "free wins" to "judgment calls" so each step leaves the repo
green-ish and the diff reviewable.

---

## Step 1 — apply the 30 safe autofixes (5 minutes)

These are mechanical and behavior-preserving: trailing commas (COM812),
unused imports (F401), import sorting (I001), whitespace/EOF (W292/W293),
`timezone.utc` alias (UP017), docstring blank lines (D202/D204), `list()`
literal (PIE807).

```bash
ruff check . --fix
mkdir -p /tmp/logs && cd /tmp && \
  ~/.pyenv/versions/3.11.7/bin/python -m pytest /home/zzuse/code/safefamily/tests
```

Commit as one "lint: autofix" commit. Do **not** pass `--unsafe-fixes`
blindly — review those separately (68 hidden fixes, some touch behavior,
e.g. rewriting `datetime` calls).

## Step 2 — stop linting tests like production code (kills ~740 findings)

The test suite legitimately uses stub lambdas (`lambda *a, **k: ...` →
ARG005 ×154), magic values in asserts (PLR2004 ×122), private access
(SLF001 ×35), naive datetimes in fixtures (DTZ ×40), imports inside tests
(PLC0415 ×20), and has no need for docstrings on every test (D1xx ×250+)
or annotations (ANN ×60). These are test idioms, not defects.

Extend `per-file-ignores` in `pyproject.toml`:

```toml
[tool.ruff]
lint.per-file-ignores = { "tests/*" = [
    "S101",     # asserts (already ignored)
    "S106",     # fake tokens/passwords in fixtures
    "ANN",      # no annotations required in tests
    "ARG",      # stub lambdas/functions with unused args
    "D",        # no docstring requirements in tests
    "PLR2004",  # magic values in asserts are fine
    "SLF001",   # tests may poke module privates
    "DTZ",      # naive datetimes in fixtures are fine
    "PLC0415",  # local imports inside tests
    "EM",       # string literals in stub exceptions are fine
    "TRY002",   # raising plain Exception in stubs is fine
    "TRY003",   # long messages in stub exceptions are fine
    "FBT",      # boolean positional args in fake helpers are fine
], "scripts/*" = [
    "INP001",   # scripts/ is not a package
    "S108",     # writes to /tmp are intentional here
] }
```

(Replaces the current `{"tests/*" = ["S101", "ANN001", "ANN202"]}`.)

> **Status: ALL STEPS (1–4) applied on 2026-07-12 — `ruff check .` is
> clean (974 → 0)**; full pytest suite green (194 passed), helpers.py at
> 100% coverage. Step 5 (pre-commit/CI lock-in, explicit rule list) is
> the only remaining item.
> Step 3 delivered: S113 timeout in log_poster, `utcnow()` →
> `datetime.now(UTC).replace(tzinfo=None)` in auth.py + notesync/service.py
> (kept naive-UTC storage semantics), tz-aware `now()` in weekly_metrics,
> dead assignments removed (todo.py ×2, auth.py, test_receiver ×2), app.py
> commented-out debug code deleted, sha1 marked `usedforsecurity=False`
> (algorithm unchanged — DB rows depend on it), S603 noqa'd with rationale
> in auto_git, DTZ007 added to `lint.ignore`. Remaining: step 4 style debt
> (ANN ×46, D1xx ×32, N815 schemas ×10, PLW0603 ×8, EM/TRY ×16, PTH123 ×6,
> complexity warnings) and PT011 ×3 / PLW0108 ×1 in tests.

## Step 3 — fix the findings that can bite at runtime (~1–2 hours)

Priority order, all in production code:

1. **S113 — `requests.post` without timeout**, `scripts/log_poster.py:45`.
   A hung AdGuard endpoint blocks the poster forever. Add
   `timeout=10` (the codebase already does this in `notifier.py` and
   `gas_weather.py`).

2. **DTZ003 — `datetime.utcnow()`**, `src/safe_family/core/auth.py:67` and
   `src/safe_family/notesync/service.py:16`. Deprecated since Python 3.12
   and returns a *naive* timestamp; auth.py uses it for token blocklist
   timestamps. Replace with `datetime.now(timezone.utc)` — same instant,
   tz-aware, future-proof. Verify any DB comparisons still match (columns
   storing naive UTC will need `.replace(tzinfo=None)` or a column-level
   decision).

3. **DTZ005 — `datetime.now()` without tz**,
   `src/safe_family/cli/weekly_metrics.py:181`. Use
   `datetime.now(local_tz)` like the rest of the codebase.

4. **F841 / RUF059 — dead assignments**: `todo.py:669` (`log_date_dt`),
   `todo.py:548` (`task`), `auth.py:238` (`data`). Delete or rename to `_`.
   Two minutes each; occasionally these reveal a forgotten validation —
   read before deleting.

5. **ERA001 — commented-out code**, `app.py:70–80` (old debug
   `after_request` logger). Delete it; git history keeps it.

6. **S324 — `hashlib.sha1`**, `src/safe_family/urls/receiver.py:68`. It's a
   dedup key, not a credential hash, so the right fix is to declare that:
   `hashlib.sha1(raw.encode(), usedforsecurity=False)`. **Caution:** do NOT
   switch algorithms — existing rows in the `ip` column hold sha1 digests
   and would all stop matching.

7. **S603 — subprocess calls**, `auto_git/auto_git.py:57,62,66`. The
   arguments are a fixed git binary path + constant args with `cwd` from
   settings — not untrusted input. Suppress with intent:
   `subprocess.check_call(...)  # noqa: S603` or add `S603` to the ignore
   list if you consider the rule noise project-wide.

8. **DTZ007 — naive `strptime`** (11 hits: `todo.py`, `scheduler.py`,
   `analyzer.py`). All parse clock strings like `"16:00"` where no date/tz
   exists; the results are immediately combined with tz-aware "now". These
   are false positives in context — add `DTZ007` to `lint.ignore` (you
   already ignore its sibling DTZ002) or `# noqa: DTZ007` the few sites if
   you want the rule kept for future code.

## Step 4 — style/structure debt in `src/` (do per-module, opportunistically)

What remains (~150) groups into five buckets. Suggested order:

1. **Intentional API casing — config, not code.** N815 ×10 is entirely
   `notesync/schemas.py` (`noteId`, `contentType`, …) matching the mobile
   app's JSON wire format. Don't rename fields — ignore per file:
   `"src/safe_family/notesync/schemas.py" = ["N815"]`.

2. **Missing annotations** (ANN001 ×26, ANN202 ×13, ANN002/003 ×8).
   Add type hints module-by-module when touching a file anyway; start with
   `utils/helpers.py` and `core/auth.py` (highest counts). Cheap and makes
   later refactors safer.

3. **Missing docstrings** (D104 ×12 package `__init__.py`, D101 ×10,
   D103 ×6, D100 ×2). One-liners are fine; `__init__.py` gets a single
   summary line. Alternatively decide docstrings-on-request and ignore
   `D1` project-wide — pick a policy once instead of accreting noqa.

4. **Exception style** (EM101 ×7, TRY003 ×6, TRY300/301/400 ×9).
   Mechanical rewrites (`raise X("msg")` → assign message first, use
   `logger.exception` in handlers). Bundle into one commit.

5. **Structural warnings — decide, don't grind.**
   - PLW0603 (`global` ×8): scheduler leader-election state is deliberate;
     `# noqa: PLW0603` with a short reason, or wrap state in a class later.
   - C901/PLR0911/0912/0915 (complexity, ~15): `todo_page()`, `auth`
     flows. Real refactors — only worth doing with test coverage in hand
     (it exists, 91%). Treat as backlog items, not lint chores.
   - PLC0415 ×1 in src: the lazy `playwright` import in
     `gas_weather.py` is deliberate (keeps the app importable without
     Playwright) — noqa with comment.

## Step 5 — lock it in

1. When `ruff check .` is clean, remove any temporary ignores you don't
   want to keep and pin the state in CI / pre-commit:

   ```yaml
   # .pre-commit-config.yaml
   repos:
     - repo: https://github.com/astral-sh/ruff-pre-commit
       rev: v0.15.20
       hooks:
         - id: ruff
   ```

2. Consider replacing `extend-select = ["ALL"]` with an explicit list
   (e.g. `E, W, F, I, B, S, DTZ, UP, RUF, PL, ARG, SIM`). `ALL` silently
   adopts every new rule on each ruff upgrade, which is how a clean repo
   drifts back to hundreds of findings.

## Suggested commit sequence

| # | Commit | Findings removed |
|---|---|---|
| 1 | `ruff check . --fix` autofixes | ~30 |
| 2 | pyproject per-file-ignores for tests/ + scripts/ | ~745 |
| 3 | runtime fixes (S113, DTZ003/005, F841, ERA001, S324) | ~15 |
| 4 | intentional suppressions (S603, DTZ007, N815, PLW0603, PLC0415) | ~35 |
| 5+ | per-module annotation/docstring/exception cleanups | rest |

Run the full pytest suite (from `/tmp`, Python 3.11.7) after every step —
steps 1 and 3 touch production code.
