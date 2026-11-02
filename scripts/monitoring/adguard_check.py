#!/usr/bin/env python3
"""Write AdGuard Home health and domain-blocking metrics for node-exporter.

Asks AdGuard's own API, so "blocked" means what AdGuard would do right now
for that name, whether by a blocked service (how SafeFamily blocks YouTube),
a filter rule or parental control. Run every minute by
deploy/systemd/safefamily-adguard.timer; settings come from the environment,
normally /etc/safefamily/adguard.env (root-only, it holds the password):

    ADGUARD_HOSTPORT         e.g. 10.0.0.1:8080 (same value as the app's .env)
    ADGUARD_USERNAME         AdGuard web login
    ADGUARD_PASSWORD
    ADGUARD_WATCH_DOMAINS    space separated, default "youtube.com"
    NODE_EXPORTER_TEXTFILE_DIR  default /var/lib/node_exporter/textfile
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TIMEOUT_SECONDS = 10
# check_host reasons that mean AdGuard answers with a block. Rewrites and
# safe search change the answer but do not block, so they are not listed.
BLOCKING_REASONS = {
    "FilteredBlackList",
    "FilteredBlockedService",
    "FilteredParental",
    "FilteredSafeBrowsing",
}


class AdGuardClient:
    """Minimal authenticated client for the AdGuard Home control API."""

    def __init__(self, hostport: str, username: str, password: str) -> None:
        """Prepare the base URL and Basic auth header."""
        self.base = hostport if "://" in hostport else f"http://{hostport}"
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.auth = f"Basic {token}"

    def get(self, path: str, **params: str) -> dict:
        """GET a control endpoint and return its JSON body."""
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        request = urllib.request.Request(  # noqa: S310 - URL built from admin config
            f"{self.base.rstrip('/')}/control/{path}{query}",
            headers={"Authorization": self.auth, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.load(response)


def collect(client: AdGuardClient, domains: list[str]) -> list[str]:
    """Return Prometheus text-format lines for one check run."""
    lines = []

    def metric(name: str, help_text: str, samples: list[tuple[str, float]]) -> None:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.extend(f"{name}{labels} {value:g}" for labels, value in samples)

    try:
        status = client.get("status")
        stats = client.get("stats")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "code", None) or getattr(exc, "reason", exc)
        print(f"[adguard_check] AdGuard API not usable: {reason}", file=sys.stderr)
        metric("safefamily_adguard_up", "1 if the AdGuard API answered with the configured login.", [("", 0)])
        return lines

    metric("safefamily_adguard_up", "1 if the AdGuard API answered with the configured login.", [("", 1)])
    metric(
        "safefamily_adguard_protection_enabled",
        "1 if AdGuard protection (filtering) is switched on.",
        [("", 1 if status.get("protection_enabled") else 0)],
    )
    metric(
        "safefamily_adguard_dns_queries",
        "DNS queries in AdGuard's statistics window (default 24h).",
        [("", float(stats.get("num_dns_queries", 0)))],
    )
    metric(
        "safefamily_adguard_blocked_queries",
        "Queries blocked by filters in AdGuard's statistics window.",
        [("", float(stats.get("num_blocked_filtering", 0)))],
    )

    blocked, check_ok = [], []
    for domain in domains:
        labels = f'{{domain="{domain}"}}'
        try:
            result = client.get("filtering/check_host", name=domain)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"[adguard_check] check_host {domain} failed: {exc}", file=sys.stderr)
            check_ok.append((labels, 0))
            continue
        reason = result.get("reason", "")
        print(f"[adguard_check] {domain}: {reason}", file=sys.stderr)
        blocked.append((labels, 1 if reason in BLOCKING_REASONS else 0))
        check_ok.append((labels, 1))
    if blocked:
        metric(
            "safefamily_adguard_domain_blocked",
            "1 if AdGuard would block this domain right now.",
            blocked,
        )
    metric("safefamily_adguard_domain_check_ok", "1 if the block check for this domain worked.", check_ok)
    return lines


def main() -> int:
    """Run one check and write the metrics file atomically."""
    hostport = os.environ.get("ADGUARD_HOSTPORT", "")
    username = os.environ.get("ADGUARD_USERNAME", "")
    password = os.environ.get("ADGUARD_PASSWORD", "")
    if not hostport or not username:
        print("[adguard_check] set ADGUARD_HOSTPORT, ADGUARD_USERNAME and ADGUARD_PASSWORD", file=sys.stderr)
        return 2
    domains = os.environ.get("ADGUARD_WATCH_DOMAINS", "youtube.com").split()
    out_dir = Path(os.environ.get("NODE_EXPORTER_TEXTFILE_DIR", "/var/lib/node_exporter/textfile"))

    lines = collect(AdGuardClient(hostport, username, password), domains)
    lines += [
        "# HELP safefamily_adguard_last_check_timestamp_seconds When adguard_check.py last ran.",
        "# TYPE safefamily_adguard_last_check_timestamp_seconds gauge",
        f"safefamily_adguard_last_check_timestamp_seconds {int(time.time())}",
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "safefamily_adguard.prom.tmp"
    tmp.write_text("\n".join(lines) + "\n")
    tmp.chmod(0o644)  # node-exporter runs as another user
    tmp.replace(out_dir / "safefamily_adguard.prom")
    return 0


if __name__ == "__main__":
    sys.exit(main())
