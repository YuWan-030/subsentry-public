from __future__ import annotations

import requests

from backend.app.core.config import Settings


VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def is_turnstile_enabled(settings: Settings) -> bool:
    return bool(settings.turnstile_enabled and settings.turnstile_site_key and settings.turnstile_secret_key)


def verify_turnstile(settings: Settings, token: str | None, remote_ip: str = "") -> tuple[bool, str]:
    if not is_turnstile_enabled(settings):
        return True, ""

    clean_token = (token or "").strip()
    if not clean_token:
        return False, "请先完成人机验证"

    try:
        response = requests.post(
            VERIFY_URL,
            json={
                "secret": settings.turnstile_secret_key,
                "response": clean_token,
                "remoteip": remote_ip,
            },
            timeout=8,
        )
        response.raise_for_status()
        result = response.json()
    except requests.RequestException:
        return False, "人机验证服务暂时不可用，请稍后重试"
    except ValueError:
        return False, "人机验证响应异常，请稍后重试"

    if result.get("success") is True:
        return True, ""
    return False, "人机验证失败，请刷新后重试"
