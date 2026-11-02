#!/usr/bin/env python3
"""Write AdGuard Home health and domain-blocking metrics for node-exporter.

Two kinds of "is it blocked":
  * services: whether a service id is in AdGuard's blocked-services list, the
    list SafeFamily switches (blocker.py). A fast, local lookup.
  * domains: AdGuard's check_host answer for a name, which also covers filter
    rules and parental control, but can be slow on a busy router or when
    Safe Browsing / Parental Control cannot reach AdGuard's servers.

Run every minute by deploy/systemd/safefamily-adguard.timer; settings come
from the environment, normally /etc/safefamily/adguard.env (root-only, it
holds the password):

    ADGUARD_HOSTPORT         e.g. 10.0.0.1:8080 (same value as the app's .env)
    ADGUARD_USERNAME         AdGuard web login
    ADGUARD_PASSWORD
    ADGUARD_WATCH_SERVICES   blocked-service ids, space separated, default "youtube"
    ADGUARD_WATCH_DOMAINS    names for check_host, default "youtube.com"; "" = off
    ADGUARD_TIMEOUT          seconds per API call, default 30
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

DEFAULT_TIMEOUT_SECONDS = 30
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

    def __init__(self, hostport: str, username: str, password: str, timeout: float) -> None:
        """Prepare the base URL and Basic auth header."""
        self.timeout = timeout
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
        with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
            return json.load(response)


def blocked_service_ids(client: AdGuardClient) -> set[str]:
    """Return the ids in AdGuard's blocked-services list (old and new API)."""
    try:
        # v0.107.37+: {"ids": [...], "schedule": {...}}
        return set(client.get("blocked_services/get").get("ids") or [])
    except urllib.error.HTTPError as exc:
        if exc.code not in (404, 405):
            raise
    # Older versions: a plain list of ids.
    return set(client.get("blocked_services/list") or [])


API_ERRORS = (urllib.error.URLError, OSError, ValueError)


class Metrics:
    """Collects Prometheus text-format lines."""

    def __init__(self) -> None:
        """Start with no lines."""
        self.lines: list[str] = []

    def add(self, name: str, help_text: str, samples: list[tuple[str, float]]) -> None:
        """Add one gauge with its HELP/TYPE header."""
        self.lines.append(f"# HELP {name} {help_text}")
        self.lines.append(f"# TYPE {name} gauge")
        self.lines.extend(f"{name}{labels} {value:g}" for labels, value in samples)


def collect_health(client: AdGuardClient, out: Metrics) -> bool:
    """Record whether AdGuard answers, protection and query counts."""
    help_up = "1 if the AdGuard API answered with the configured login."
    try:
        status = client.get("status")
        stats = client.get("stats")
    except API_ERRORS as exc:
        reason = getattr(exc, "code", None) or getattr(exc, "reason", exc)
        print(f"[adguard_check] AdGuard API not usable: {reason}", file=sys.stderr)
        out.add("safefamily_adguard_up", help_up, [("", 0)])
        return False
    out.add("safefamily_adguard_up", help_up, [("", 1)])
    out.add(
        "safefamily_adguard_protection_enabled",
        "1 if AdGuard protection (filtering) is switched on.",
        [("", 1 if status.get("protection_enabled") else 0)],
    )
    out.add(
        "safefamily_adguard_dns_queries",
        "DNS queries in AdGuard's statistics window (default 24h).",
        [("", float(stats.get("num_dns_queries", 0)))],
    )
    out.add(
        "safefamily_adguard_blocked_queries",
        "Queries blocked by filters in AdGuard's statistics window.",
        [("", float(stats.get("num_blocked_filtering", 0)))],
    )
    return True


def collect_services(client: AdGuardClient, services: list[str], out: Metrics) -> None:
    """Record whether each service id is in the blocked-services list."""
    if not services:
        return
    try:
        ids = blocked_service_ids(client)
    except API_ERRORS as exc:
        print(f"[adguard_check] blocked services lookup failed: {exc}", file=sys.stderr)
        return
    for service in services:
        state = "blocked" if service in ids else "allowed"
        print(f"[adguard_check] service {service}: {state}", file=sys.stderr)
    out.add(
        "safefamily_adguard_service_blocked",
        "1 if this service id is in AdGuard's blocked-services list.",
        [(f'{{service="{service}"}}', 1 if service in ids else 0) for service in services],
    )


def collect_domains(client: AdGuardClient, domains: list[str], out: Metrics) -> None:
    """Record AdGuard's check_host verdict for each domain."""
    blocked, check_ok = [], []
    for domain in domains:
        labels = f'{{domain="{domain}"}}'
        try:
            result = client.get("filtering/check_host", name=domain)
        except API_ERRORS as exc:
            hint = ""
            if "timed out" in str(exc):
                hint = (
                    f" (after {client.timeout:g}s; check_host is slow when Safe Browsing/Parental"
                    " Control cannot reach AdGuard's servers: raise ADGUARD_TIMEOUT, or rely on"
                    ' ADGUARD_WATCH_SERVICES and set ADGUARD_WATCH_DOMAINS="")'
                )
            print(f"[adguard_check] check_host {domain} failed: {exc}{hint}", file=sys.stderr)
            check_ok.append((labels, 0))
            continue
        reason = result.get("reason", "")
        print(f"[adguard_check] {domain}: {reason}", file=sys.stderr)
        blocked.append((labels, 1 if reason in BLOCKING_REASONS else 0))
        check_ok.append((labels, 1))
    if blocked:
        out.add("safefamily_adguard_domain_blocked", "1 if AdGuard would block this domain right now.", blocked)
    if check_ok:
        out.add("safefamily_adguard_domain_check_ok", "1 if the block check for this domain worked.", check_ok)


def collect(client: AdGuardClient, services: list[str], domains: list[str]) -> list[str]:
    """Return Prometheus text-format lines for one check run."""
    out = Metrics()
    if collect_health(client, out):
        collect_services(client, services, out)
        collect_domains(client, domains, out)
    return out.lines


def main() -> int:
    """Run one check and write the metrics file atomically."""
    hostport = os.environ.get("ADGUARD_HOSTPORT", "")
    username = os.environ.get("ADGUARD_USERNAME", "")
    password = os.environ.get("ADGUARD_PASSWORD", "")
    if not hostport or not username:
        print("[adguard_check] set ADGUARD_HOSTPORT, ADGUARD_USERNAME and ADGUARD_PASSWORD", file=sys.stderr)
        return 2
    services = os.environ.get("ADGUARD_WATCH_SERVICES", "youtube").split()
    domains = os.environ.get("ADGUARD_WATCH_DOMAINS", "youtube.com").split()
    try:
        timeout = float(os.environ.get("ADGUARD_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    out_dir = Path(os.environ.get("NODE_EXPORTER_TEXTFILE_DIR", "/var/lib/node_exporter/textfile"))

    lines = collect(AdGuardClient(hostport, username, password, timeout), services, domains)
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
