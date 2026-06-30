# SafeFamily redesign — drop-in templates

Two Jinja templates plus a new `base.html` for the **Quest** direction (dark + your orange,
framed as a daily quest for the kids, with the rainbow progress bar as the centerpiece).
A **Hearth** (light) palette is included as a one-line CSS variable switch in `base.html`.

## What's in here

```
templates_redesign/
├── base.html                       ← replaces src/safe_family/templates/base.html
├── todo/todo.html                  ← replaces src/safe_family/templates/todo/todo.html
├── rules/schedule_rules.html       ← replaces src/safe_family/templates/rules/schedule_rules.html
└── README.md                       ← this file
```

## How to install

1. Back up your current `templates/` folder.
2. Copy the three files above into the matching paths under
   `src/safe_family/templates/`.
3. No Python changes needed — every Flask `url_for()` endpoint, form action, hidden
   input, and class/ID your JS depends on is preserved (`complete-checkbox`,
   `admin-status-select`, `time-slot-cell` with `--slot-progress`, `bridge-element`,
   all the `*-modal` IDs, etc.).
4. Tailwind: your existing `styles.css` is still loaded, so anything else that
   uses utility classes keeps working unchanged. You do **not** need to rerun
   the Tailwind CLI for the redesign — the new look ships as scoped CSS inside
   the templates.

## Switching to the Hearth (light) palette

Open `base.html`, find the `:root` block in the `<style>` element, and swap it with
the commented-out `:root` block right below — it overrides all CSS variables to the
warm cream palette in one go. No HTML changes.

## What's intentionally new

- **`base.html`** — single top bar (logo · nav · user), proper `.active` state on nav
  links, system font stack switched to Space Grotesk + Geist + JetBrains Mono,
  and a footer that matches.
- **`todo/todo.html`** — hero greeting + streak / xp / pct stat tiles, the rainbow
  progress bar rendered per-task (segment is glowing if done, outlined if current,
  dim if pending), a two-column "missions + planner" grid, mandatory-tag chips,
  and a **reserved card for your calendar heatmap** so the slot is there waiting
  when you build it. All your existing JS hooks are intact.
- **`rules/schedule_rules.html`** — a 24-hour day-timeline at the top showing every
  active rule's window with a "now" marker, the rule table redesigned with
  inline day-pill toggles instead of separate enable/disable forms, and the
  agile-config calculator preserved exactly (formula and field names unchanged).

## Things that are stubbed and need backend wiring

These are placeholders that render but show `—` or example data until you wire
real values in your route:

- **`streak`** — context var checked in `todo.html` (`{% if streak is defined %}`).
  Pass it from your route to show the streak tile.
- **This-week strip** in `todo.html` — currently shows dashes; pass a 7-element
  list of completion percentages (or replace with your weekly summary data).
- **Activity heatmap reserved card** — intentionally empty. When you build the
  history endpoint, render a 7×12 grid into the `.sf-heatmap-reserve` card and
  reuse the orange shade scale you already see in the canvas mockup.

## Other pages

Same recipe applies to the rest of your templates (notes, timeline, suspicious_view,
auth, etc.). The CSS variables and helper classes in `base.html` cover them already —
mostly it's a matter of swapping `class="card"` divs and table markup to use the
same patterns. Ping me and I'll port them next.
