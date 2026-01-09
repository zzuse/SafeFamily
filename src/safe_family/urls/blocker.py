"""Blocker URL routes for Safe Family application."""

import logging

import requests
from flask import Blueprint, flash, redirect

from config.settings import settings
from src.safe_family.core.auth import admin_required, login_required
from src.safe_family.utils.constants import HTTP_OK

logger = logging.getLogger(__name__)
headers = {
    "Content-Type": "application/json",
}
rules_toggle_bp = Blueprint("rules_toggle", __name__)
"""
curl -u $USERNAME:$PASSWORD ${ADGUARD_HOST}/control/filtering/status
curl -u $USERNAME:$PASSWORD ${ADGUARD_HOST}/control/blocked_services/all
"""


def json_post(json_data: dict) -> requests.Response:
    """Send a POST request to the AdGuard Home API."""
    return requests.post(
        "http://" + f"{settings.ADGUARD_HOSTPORT}/control/filtering/set_url",
        headers=headers,
        json=json_data,
        auth=(f"{settings.ADGUARD_USERNAME}", f"{settings.ADGUARD_PASSWORD}"),
        timeout=10.0,
    )


def rule_enable_all_except_ai():
    """Enable all blocking rules except AI."""
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_game.txt",
        "data": {
            "name": "Game",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_game.txt",
            "enabled": True,
        },
        "whitelist": False,
    }
    response = json_post(json_data)
    logger.info("Game Response status: %d", response.status_code)
    logger.info("Game Response status: %s", response.text)
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_music.txt",
        "data": {
            "name": "Music",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_music.txt",
            "enabled": True,
        },
        "whitelist": False,
    }
    response = json_post(json_data)
    logger.info("Music Response status: %d", response.status_code)
    logger.info("Music Response status: %s", response.text)
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_news.txt",
        "data": {
            "name": "News",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_news.txt",
            "enabled": True,
        },
        "whitelist": False,
    }
    response = json_post(json_data)
    logger.info("News Response status: %d", response.status_code)
    logger.info("News Response status: %s", response.text)
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_video.txt",
        "data": {
            "name": "Video",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_video.txt",
            "enabled": True,
        },
        "whitelist": False,
    }
    response = json_post(json_data)
    logger.info("Video Response status: %d", response.status_code)
    logger.info("Video Response status: %s", response.text)
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_a03s.txt",
        "data": {
            "name": "A03S",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_a03s.txt",
            "enabled": True,
        },
        "whitelist": False,
    }
    response = json_post(json_data)
    logger.info("A03S Response status: %d", response.status_code)
    logger.info("A03S Response status: %s", response.text)
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/allow_educational.txt",
        "data": {
            "name": "scratch",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/allow_educational.txt",
            "enabled": True,
        },
        "whitelist": True,
    }
    response = json_post(json_data)
    logger.info("scratch Response status: %d", response.status_code)
    logger.info("scratch Response status: %s", response.text)

    json_data = {
        "ids": [
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
            "xboxlive",
            "xiaohongshu",
            "yy",
            "reddit",
            "riot_games",
            "valorant",
            "amazon_streaming",
            "zhihu",
            "minecraft",
            "twitch",
            "steam",
            "apple_streaming",
            "snapchat",
            "discord",
            "youtube",
            "roblox",
        ],
        "schedule": {
            "time_zone": "UTC",
        },
    }
    response = requests.put(
        "http://" + f"{settings.ADGUARD_HOSTPORT}/control/blocked_services/update",
        headers=headers,
        json=json_data,
        auth=(f"{settings.ADGUARD_USERNAME}", f"{settings.ADGUARD_PASSWORD}"),
        timeout=10.0,
    )
    logger.info("Service Response status: %d", response.status_code)
    logger.info("Service Response status: %s", response.text)
    return response


def rule_enable_ai():
    """Enable only AI blocking rule."""
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_ai.txt",
        "data": {
            "name": "AI",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_ai.txt",
            "enabled": True,
        },
        "whitelist": False,
    }
    return json_post(json_data)


def rule_disable_ai():
    """Disable only AI blocking rule."""
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_ai.txt",
        "data": {
            "name": "AI",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_ai.txt",
            "enabled": False,
        },
        "whitelist": False,
    }
    return json_post(json_data)


def rule_disable_all():
    """Disable all blocking rules."""
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_game.txt",
        "data": {
            "name": "Game",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_game.txt",
            "enabled": False,
        },
        "whitelist": False,
    }
    response = json_post(json_data)

    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_music.txt",
        "data": {
            "name": "Music",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_music.txt",
            "enabled": False,
        },
        "whitelist": False,
    }
    response = json_post(json_data)

    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_news.txt",
        "data": {
            "name": "News",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_news.txt",
            "enabled": False,
        },
        "whitelist": False,
    }
    response = json_post(json_data)

    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_clicker.txt",
        "data": {
            "name": "Clicker",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_clicker.txt",
            "enabled": False,
        },
        "whitelist": False,
    }
    response = json_post(json_data)

    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_video.txt",
        "data": {
            "name": "Video",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_video.txt",
            "enabled": False,
        },
        "whitelist": False,
    }
    response = json_post(json_data)

    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_ai.txt",
        "data": {
            "name": "AI",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_ai.txt",
            "enabled": False,
        },
        "whitelist": False,
    }
    response = json_post(json_data)
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_a03s.txt",
        "data": {
            "name": "A03S",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/block_a03s.txt",
            "enabled": False,
        },
        "whitelist": False,
    }
    response = json_post(json_data)
    json_data = {
        "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/allow_educational.txt",
        "data": {
            "name": "scratch",
            "url": "https://raw.githubusercontent.com/zzuse/adguard_home_rule/refs/heads/main/allow_educational.txt",
            "enabled": True,
        },
        "whitelist": True,
    }
    response = json_post(json_data)
    json_data = {
        "ids": [
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
        ],
        "schedule": {
            "time_zone": "UTC",
        },
    }
    return requests.put(
        "http://" + f"{settings.ADGUARD_HOSTPORT}/control/blocked_services/update",
        headers=headers,
        json=json_data,
        auth=(f"{settings.ADGUARD_USERNAME}", f"{settings.ADGUARD_PASSWORD}"),
        timeout=10.0,
    )


def rule_stop_traffic_all():
    """Stop all traffic by disabling the gateway on the router."""
    response = requests.get(
        f"http://{settings.ROUTER_IP}/cgi-bin/disablegateway.sh",
        timeout=10.0,
    )
    logger.info("Response status: %d", response.status_code)
    return response


def rule_allow_traffic_all():
    """Allow all traffic by enabling the gateway on the router."""
    response = requests.get(
        f"http://{settings.ROUTER_IP}/cgi-bin/enablegateway.sh",
        timeout=10.0,
    )  # GET request, same as curl without -X
    logger.info("Response status: %d", response.status_code)
    return response


def rule_status_gateway():
    """Check the status of the gateway on the router."""
    response = requests.get(
        f"http://{settings.ROUTER_IP}/cgi-bin/gateway.sh",
        timeout=10.0,
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
    logger.info("Disable Response status: %d", response.status_code)
    return redirect("/")


@rules_toggle_bp.route("/rules_toggle/disable_ai", methods=["POST"])
@login_required
def rules_disable_ai():
    """Disable AI rules."""
    response = rule_disable_ai()
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
