"""Blocker URL routes for Safe Family application."""

import logging
import threading
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Blueprint, flash, redirect

from config.settings import settings
from src.safe_family.core.auth import admin_required, login_required
from src.safe_family.utils.constants import HTTP_OK

logger = logging.getLogger(__name__)
headers = {"Content-Type": "application/json"}
REQUEST_TIMEOUT = 10.0
ADGUARD_BASE_URL = f"http://{settings.ADGUARD_HOSTPORT}"
ROUTER_BASE_URL = f"http://{settings.ROUTER_IP}"
ADGUARD_AUTH = (f"{settings.ADGUARD_USERNAME}", f"{settings.ADGUARD_PASSWORD}")
SESSION = requests.Session()
DISABLE_AI_LOCK = threading.Lock()
DISABLE_AI_COOLDOWN_SECONDS = 300.0
DISABLE_AI_STATE = {"last_run": 0.0}
rules_toggle_bp = Blueprint("rules_toggle", __name__)
"""
curl -u $USERNAME:$PASSWORD ${ADGUARD_HOST}/control/filtering/status
curl -u $USERNAME:$PASSWORD ${ADGUARD_HOST}/control/blocked_services/all
"""


def json_post(json_data: dict) -> requests.Response:
    """Send a POST request to the AdGuard Home API."""
    return SESSION.post(
        f"{ADGUARD_BASE_URL}/control/filtering/set_url",
        headers=headers,
        json=json_data,
        auth=ADGUARD_AUTH,
        timeout=REQUEST_TIMEOUT,
    )


def _post_filter_rule(
    *,
    name: str,
    url: str,
    enabled: bool,
    whitelist: bool,
) -> requests.Response:
    """Update a single filter rule in AdGuard."""
    json_data = {
        "url": url,
        "data": {"name": name, "url": url, "enabled": enabled},
        "whitelist": whitelist,
    }
    return json_post(json_data)


BLOCKED_SERVICE_IDS_DISABLE = [
    "4chan",
    "500px",
    "9gag",
    "activision_blizzard",
    "aliexpress",
    "amazon",
    "amino",
    "battle_net",
    "betano",
    "betfair",
    "betway",
    "bigo_live",
    "bilibili",
    "blaze",
    "blizzard_entertainment",
    "bluesky",
    "box",
    "canais_globo",
    "claro",
    "cloudflare",
    "clubhouse",
    "coolapk",
    "crunchyroll",
    "dailymotion",
    "deezer",
    "directvgo",
    "discoveryplus",
    "disneyplus",
    "douban",
    "dropbox",
    "ebay",
    "electronic_arts",
    "epic_games",
    "espn",
    "facebook",
    "fifa",
    "flickr",
    "globoplay",
    "gog",
    "hbomax",
    "hulu",
    "icloud_private_relay",
    "iheartradio",
    "imgur",
    "instagram",
    "iqiyi",
    "kakaotalk",
    "kik",
    "kook",
    "lazada",
    "leagueoflegends",
    "line",
    "linkedin",
    "lionsgateplus",
    "looke",
    "mail_ru",
    "mastodon",
    "mercado_libre",
    "nebula",
    "netflix",
    "nintendo",
    "nvidia",
    "ok",
    "olvid",
    "onlyfans",
    "origin",
    "paramountplus",
    "peacock_tv",
    "pinterest",
    "playstation",
    "plenty_of_fish",
    "plex",
    "pluto_tv",
    "privacy",
    "qq",
    "rakuten_viki",
    "rockstar_games",
    "samsung_tv_plus",
    "shein",
    "shopee",
    "signal",
    "slack",
    "soundcloud",
    "spotify",
    "telegram",
    "temu",
    "tidal",
    "tiktok",
    "tinder",
    "tumblr",
    "twitter",
    "ubisoft",
    "viber",
    "vimeo",
    "vk",
    "voot",
    "wargaming",
    "wechat",
    "weibo",
    "whatsapp",
    "wizz",
    "xiaohongshu",
    "yy",
    "reddit",
    "riot_games",
    "valorant",
    "amazon_streaming",
    "zhihu",
    "twitch",
]

BLOCKED_SERVICE_IDS_ENABLE = [
    "xboxlive",
    "minecraft",
    "steam",
    "apple_streaming",
    "snapchat",
    "discord",
    "youtube",
    "roblox",
]

BLOCKED_SERVICE_IDS_ENABLE_JOINT = list(
    dict.fromkeys(BLOCKED_SERVICE_IDS_DISABLE + BLOCKED_SERVICE_IDS_ENABLE),
)


def _update_blocked_services(ids: list[str]) -> requests.Response:
    """Update blocked services in AdGuard."""
    json_data = {"ids": ids, "schedule": {"time_zone": "UTC"}}
    return SESSION.put(
        f"{ADGUARD_BASE_URL}/control/blocked_services/update",
        headers=headers,
        json=json_data,
        auth=ADGUARD_AUTH,
        timeout=REQUEST_TIMEOUT,
    )


def _run_rule_updates(rules: list[dict]) -> None:
    """Send multiple rule updates in parallel."""
    if not rules:
        return
    with ThreadPoolExecutor(max_workers=min(6, len(rules))) as executor:
        futures = {
            executor.submit(
                _post_filter_rule,
                name=rule["name"],
                url=rule["url"],
                enabled=rule["enabled"],
                whitelist=rule["whitelist"],
            ): rule
            for rule in rules
        }
        for future in as_completed(futures):
            rule = futures[future]
            try:
                response = future.result()
            except requests.ReadTimeout:
                logger.warning("Rule update timed out: %s", rule["name"])
                continue
            except Exception:
                logger.exception("Rule update failed: %s", rule["name"])
                continue
            logger.info("Rule %s status: %d", rule["name"], response.status_code)
            logger.debug("Rule %s body: %s", rule["name"], response.text)


def rule_enable_all_except_ai():
    """Enable all blocking rules except AI."""
    rules = [
        {
            "name": "Game",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_game.txt",
            "enabled": True,
            "whitelist": False,
        },
        {
            "name": "Music",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_music.txt",
            "enabled": True,
            "whitelist": False,
        },
        {
            "name": "News",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_news.txt",
            "enabled": True,
            "whitelist": False,
        },
        {
            "name": "Video",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_video.txt",
            "enabled": True,
            "whitelist": False,
        },
        {
            "name": "A03S",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_a03s.txt",
            "enabled": True,
            "whitelist": False,
        },
        {
            "name": "scratch",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/allow_educational.txt",
            "enabled": True,
            "whitelist": True,
        },
    ]
    _run_rule_updates(rules)
    response = _update_blocked_services(BLOCKED_SERVICE_IDS_ENABLE_JOINT)
    logger.info("Enable Response status: %d", response.status_code)
    logger.debug("Enable Response body: %s", response.text)
    return response


def rule_enable_ai():
    """Enable only AI blocking rule."""
    return _post_filter_rule(
        name="AI",
        url="https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_ai.txt",
        enabled=True,
        whitelist=False,
    )


def rule_disable_ai():
    """Disable only AI blocking rule."""
    return _post_filter_rule(
        name="AI",
        url="https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_ai.txt",
        enabled=False,
        whitelist=False,
    )


def rule_disable_all():
    """Disable all blocking rules."""
    rules = [
        {
            "name": "Game",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_game.txt",
            "enabled": False,
            "whitelist": False,
        },
        {
            "name": "Music",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_music.txt",
            "enabled": False,
            "whitelist": False,
        },
        {
            "name": "News",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_news.txt",
            "enabled": False,
            "whitelist": False,
        },
        {
            "name": "Clicker",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_clicker.txt",
            "enabled": False,
            "whitelist": False,
        },
        {
            "name": "Video",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_video.txt",
            "enabled": False,
            "whitelist": False,
        },
        {
            "name": "AI",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_ai.txt",
            "enabled": False,
            "whitelist": False,
        },
        {
            "name": "A03S",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_a03s.txt",
            "enabled": False,
            "whitelist": False,
        },
        {
            "name": "scratch",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/allow_educational.txt",
            "enabled": True,
            "whitelist": True,
        },
    ]
    _run_rule_updates(rules)
    response = _update_blocked_services(BLOCKED_SERVICE_IDS_DISABLE)
    logger.info("Disable Response status: %d", response.status_code)
    logger.debug("Disable Response body: %s", response.text)
    return response


def rule_stop_traffic_all():
    """Stop all traffic by disabling the gateway on the router."""
    response = SESSION.get(
        f"{ROUTER_BASE_URL}/cgi-bin/disablegateway.sh",
        timeout=REQUEST_TIMEOUT,
    )
    logger.info("Response status: %d", response.status_code)
    return response


def rule_allow_traffic_all():
    """Allow all traffic by enabling the gateway on the router."""
    response = SESSION.get(
        f"{ROUTER_BASE_URL}/cgi-bin/enablegateway.sh",
        timeout=REQUEST_TIMEOUT,
    )  # GET request, same as curl without -X
    logger.info("Response status: %d", response.status_code)
    return response


def rule_status_gateway():
    """Check the status of the gateway on the router."""
    response = SESSION.get(
        f"{ROUTER_BASE_URL}/cgi-bin/gateway.sh",
        timeout=REQUEST_TIMEOUT,
    )
    logger.info("Response status: %d", response.status_code)
    return response


@rules_toggle_bp.route("/rules_toggle/enable_all")
@admin_required
def rules_toggle_enable():
    """Enable all blocking rules except AI."""
    response = rule_enable_all_except_ai()
    flash(
        "rules enabled all.",
        (response.status_code == HTTP_OK and "success") or "danger",
    )
    logger.info("Enable Response status: %d", response.status_code)
    return redirect("/")


@rules_toggle_bp.route("/rules_toggle/disable_all")
@admin_required
def rules_toggle_disable():
    """Disable all blocking rules."""
    response = rule_disable_all()
    flash(
        "rules disabled all.",
        (response.status_code == HTTP_OK and "success") or "danger",
    )
    logger.info("Admin Disable Response status: %d", response.status_code)
    return redirect("/")


@rules_toggle_bp.route("/rules_toggle/disable_ai", methods=["POST"])
@login_required
def rules_disable_ai():
    """Disable AI rules."""
    if not DISABLE_AI_LOCK.acquire(blocking=False):
        flash("AI rule update already in progress.", "warning")
        return redirect("/")
    now = time_module.monotonic()
    remaining = DISABLE_AI_COOLDOWN_SECONDS - (now - DISABLE_AI_STATE["last_run"])
    if remaining > 0:
        DISABLE_AI_LOCK.release()
        flash(f"Please wait {remaining:.0f}s before trying again.", "warning")
        return redirect("/")
    DISABLE_AI_STATE["last_run"] = now
    try:
        response = rule_disable_ai()
    finally:
        DISABLE_AI_LOCK.release()
    flash(
        "Open AI.",
        (response.status_code == HTTP_OK and "success") or "danger",
    )
    return redirect("/")


@rules_toggle_bp.route("/rules_toggle/stop_all_traffic")
@admin_required
def stop_all_traffic():
    """Stop all traffic by disabling the gateway on the router."""
    response = rule_stop_traffic_all()
    flash(response.text, "info")
    return redirect("/")


@rules_toggle_bp.route("/rules_toggle/enable_all_traffic")
@admin_required
def enable_all_traffic():
    """Allow all traffic by enabling the gateway on the router."""
    response = rule_allow_traffic_all()
    flash(response.text, "info")
    return redirect("/")


@rules_toggle_bp.route("/rules_toggle/check_all_traffic")
@admin_required
def check_all_traffic():
    """Check the status of the gateway on the router."""
    response = rule_status_gateway()
    flash(response.text, "info")
    return redirect("/")
