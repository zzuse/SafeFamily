#!/usr/bin/env python3
"""Build the 1280x800 display dashboard from panels of the overview dashboard.

Copies the Status and AdGuard panels (same queries, mappings and colors) into
deploy/monitoring/grafana/dashboards/safefamily-display.json, laid out to fill
one 1280x800 screenshot in kiosk mode. Rerun after changing those panels:

    python3 deploy/monitoring/display-export/make_display_dashboard.py
"""

import copy
import json
from pathlib import Path

DASHBOARDS = Path(__file__).resolve().parents[1] / "grafana" / "dashboards"

# (title in the overview dashboard, x, y, w, h) on Grafana's 24-column grid.
LAYOUT = [
    ("Website", 0, 0, 6, 5),
    ("Database", 6, 0, 6, 5),
    ("App containers running", 12, 0, 6, 5),
    ("Lowest disk free", 18, 0, 6, 5),
    ("Page load time", 0, 5, 6, 5),
    ("TLS cert expires in", 6, 5, 6, 5),
    ("Last DB backup", 12, 5, 6, 5),
    ("Database size", 18, 5, 6, 5),
    ("AdGuard", 0, 10, 4, 5),
    ("Protection", 4, 10, 4, 5),
    ("Blocked now", 8, 10, 8, 5),
    ("Blocked queries (24h)", 16, 10, 4, 5),
    ("DNS queries (24h)", 20, 10, 4, 5),
    ("Blocking timeline", 0, 15, 24, 5),
]


def main() -> None:
    """Write the display dashboard JSON."""
    overview = json.loads((DASHBOARDS / "safefamily-overview.json").read_text())
    by_title = {}
    for p in overview["panels"]:
        # First panel with a title wins: "Database size" is both the Status
        # tile and, further down, a graph.
        if p.get("type") != "row":
            by_title.setdefault(p["title"], p)
    panels = []
    for panel_id, (title, x, y, w, h) in enumerate(LAYOUT, start=1):
        panel = copy.deepcopy(by_title[title])
        panel["id"] = panel_id
        panel["gridPos"] = {"x": x, "y": y, "w": w, "h": h}
        panel["description"] = ""  # no info icons on the display
        if panel["type"] == "state-timeline":
            # Rows are labelled already; the legend would only show thresholds.
            panel["options"]["legend"] = {"showLegend": False}
        panels.append(panel)
    dashboard = {
        "uid": "safefamily-display",
        "title": "SafeFamily Display",
        "tags": ["safefamily", "display"],
        "timezone": "browser",
        "schemaVersion": overview["schemaVersion"],
        "version": 1,
        "editable": False,
        "refresh": "",
        "time": {"from": "now-24h", "to": "now"},
        # No time picker bar: the whole 1280x800 is panels.
        "timepicker": {"hidden": True},
        "panels": panels,
        "templating": {"list": []},
        "annotations": {"list": []},
    }
    out = DASHBOARDS / "safefamily-display.json"
    out.write_text(json.dumps(dashboard, indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
