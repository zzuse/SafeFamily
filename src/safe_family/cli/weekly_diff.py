# CLI wrapper with __main__
# python3 -m safe_family.cli.weekly_diff --files metrics/2025-W52.txt metrics/2026-W01.txt
"""Generate a summary between two weekly metric files."""

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WeekMetrics:
    week: str
    completion_rate: float | None
    avg_tasks_per_day: float | None
    avg_planned_minutes: float | None
    by_category: dict[str, float]
    by_category_minutes: dict[str, dict[str, float]]


def _read_metrics(path: Path) -> WeekMetrics:
    data = json.loads(path.read_text(encoding="utf-8"))
    return WeekMetrics(
        week=str(data.get("week", "")),
        completion_rate=data.get("completion_rate"),
        avg_tasks_per_day=data.get("avg_tasks_per_day"),
        avg_planned_minutes=data.get("avg_planned_minutes"),
        by_category=data.get("by_category", {}),
        by_category_minutes=data.get("by_category_minutes", {}),
    )


def _is_nan(value: float | None) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _trend_arrow(current: float | None, previous: float | None) -> str:
    if current is None or previous is None or _is_nan(current) or _is_nan(previous):
        return "→"
    if current > previous:
        return "↑"
    if current < previous:
        return "↓"
    return "→"


def _delta_text(
    current: float | None,
    previous: float | None,
    fmt: str,
    scale: float = 1.0,
) -> str:
    if current is None or previous is None or _is_nan(current) or _is_nan(previous):
        return "(→)"
    delta = (current - previous) * scale
    sign = "+" if delta >= 0 else ""
    return f"({sign}{fmt.format(delta)})"


def _fmt_pct(value: float | None) -> str:
    if value is None or _is_nan(value):
        return "n/a"
    return f"{value * 100:.1f}%"


def _fmt_num(value: float | None, digits: int = 2) -> str:
    if value is None or _is_nan(value):
        return "n/a"
    return f"{value:.{digits}f}"


def _format_output(current: WeekMetrics, previous: WeekMetrics) -> str:
    study_tags = {"coding", "language", "math", "piano", "science"}
    lines: list[str] = []
    lines.append(f"WEEK: {current.week}")
    lines.append("")
    lines.append("Overall:")

    comp_arrow = _trend_arrow(current.completion_rate, previous.completion_rate)
    comp_delta = _delta_text(
        current.completion_rate,
        previous.completion_rate,
        "{:.1f}%",
        scale=100.0,
    )
    lines.append(
        f"- Completion rate: {_fmt_pct(current.completion_rate)} ({comp_arrow}) {comp_delta}",
    )

    tasks_arrow = _trend_arrow(current.avg_tasks_per_day, previous.avg_tasks_per_day)
    tasks_delta = _delta_text(
        current.avg_tasks_per_day,
        previous.avg_tasks_per_day,
        "{:.2f}",
    )
    lines.append(
        f"- Avg tasks/day: {_fmt_num(current.avg_tasks_per_day, 2)} ({tasks_arrow}) {tasks_delta}",
    )

    planned_arrow = _trend_arrow(
        current.avg_planned_minutes,
        previous.avg_planned_minutes,
    )
    planned_delta = _delta_text(
        current.avg_planned_minutes,
        previous.avg_planned_minutes,
        "{:.0f} min",
    )
    planned_value = "n/a"
    if current.avg_planned_minutes is not None and not _is_nan(
        current.avg_planned_minutes,
    ):
        planned_value = f"{current.avg_planned_minutes:.0f} min"
    lines.append(
        f"- Avg planned task length: {planned_value} ({planned_arrow}) {planned_delta}",
    )

    total_study_minutes = 0.0
    total_study_effective_minutes = 0.0
    for tag in study_tags:
        minutes = current.by_category_minutes.get(tag, {})
        total_study_minutes += minutes.get("planned_minutes", 0.0)
        total_study_effective_minutes += minutes.get("effective_minutes", 0.0)
    total_study_hours = total_study_minutes / 60.0
    total_study_effective_hours = total_study_effective_minutes / 60.0
    lines.append(f"- Total study hours (planned): {total_study_hours:.2f}h")
    lines.append(
        f"- Total study hours (effective): {total_study_effective_hours:.2f}h"
    )

    lines.append("")
    lines.append("By category:")
    if not current.by_category:
        lines.append("- n/a")
    else:
        for tag, rate in sorted(current.by_category.items()):
            prev_rate = previous.by_category.get(tag)
            arrow = _trend_arrow(rate, prev_rate)
            minutes = current.by_category_minutes.get(tag, {})
            planned_hours = minutes.get("planned_minutes", 0.0) / 60.0
            effective_hours = minutes.get("effective_minutes", 0.0) / 60.0
            lines.append(
                f"- {tag}: completion {_fmt_pct(rate)} ({arrow}), planned {planned_hours:.2f}h, effective {effective_hours:.2f}h",
            )

    lines.append("")
    lines.append("Interpretation hints:")
    if (
        current.completion_rate is not None
        and previous.completion_rate is not None
        and current.completion_rate < previous.completion_rate
    ):
        lines.append("- Overall completion declined noticeably.")
    if (
        current.avg_planned_minutes is not None
        and previous.avg_planned_minutes is not None
        and current.avg_planned_minutes > previous.avg_planned_minutes
    ):
        lines.append("- Tasks may be planned longer than before.")
    if (
        current.avg_tasks_per_day is not None
        and previous.avg_tasks_per_day is not None
        and current.avg_tasks_per_day > previous.avg_tasks_per_day
    ):
        lines.append("- Daily workload increased significantly.")
    leisure_minutes = current.by_category_minutes.get("leasure", {})
    leisure_hours = leisure_minutes.get("planned_minutes", 0.0) / 60.0
    if leisure_hours > 0:
        lines.append(
            f"- Leisure(sleep, phone, eat, etc.) time logged {leisure_hours:.2f}h; review if this should be planned study time.",
        )
    if lines[-1] == "Interpretation hints:":
        lines.append("- No major shifts detected.")

    return "\n".join(lines)


def main(args: list[str] | None = None) -> int:
    """Render a summary between two metric files."""
    parser = argparse.ArgumentParser(
        description="Generate a summary between two weekly metrics files",
    )
    parser.add_argument(
        "--files",
        nargs=2,
        metavar=("A", "B"),
        required=True,
        help="Two metric files to diff",
    )
    parsed_args = parser.parse_args(args)

    file_a = Path(parsed_args.files[0])
    file_b = Path(parsed_args.files[1])

    if not file_a.exists() or not file_b.exists():
        missing = [str(p) for p in (file_a, file_b) if not p.exists()]
        print(f"Missing file(s): {', '.join(missing)}", file=sys.stderr)
        return 1

    metrics_a = _read_metrics(file_a)
    metrics_b = _read_metrics(file_b)

    summary_text = _format_output(metrics_b, metrics_a)
    print(summary_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
