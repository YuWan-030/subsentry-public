from __future__ import annotations

import secrets
import urllib3
from typing import Any, Dict
from urllib.parse import urlencode

import requests
from fastapi import HTTPException, status

from backend.app.core.config import Settings


SESSION_ONAUTH_STATE_PREFIX = "onauth_state:"


def _verify_ssl(settings: Settings) -> bool:
    if settings.onauth_verify_ssl:
        return True
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return False


def ensure_onauth_config(settings: Settings) -> None:
    if not settings.onauth_base_url or not settings.onauth_client_id or not settings.onauth_client_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OnAuth 未配置")


def build_authorize_url(settings: Settings, redirect_uri: str, mode: str) -> tuple[str, str]:
    ensure_onauth_config(settings)
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.onauth_client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": settings.onauth_scope or "read",
        "state": state,
    }
    if mode == "bind":
        params["scope"] = settings.onauth_scope or "read"
    return f"{settings.onauth_base_url}/oauth/authorize?{urlencode(params)}", state


def exchange_code_for_token(settings: Settings, code: str, redirect_uri: str) -> Dict[str, Any]:
    ensure_onauth_config(settings)
    response = requests.post(
        f"{settings.onauth_base_url}/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": settings.onauth_client_id,
            "client_secret": settings.onauth_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=12,
        verify=_verify_ssl(settings),
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"OnAuth 换取 token 失败：{response.text[:200]}")
    return response.json()


def fetch_userinfo(settings: Settings, access_token: str) -> Dict[str, Any]:
    ensure_onauth_config(settings)
    response = requests.get(
        f"{settings.onauth_base_url}/oauth/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=12,
        verify=_verify_ssl(settings),
    )
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"OnAuth 获取用户信息失败：{response.text[:200]}")
    return response.json()


def normalize_userinfo(userinfo: Dict[str, Any]) -> Dict[str, str]:
    raw = userinfo.get("data") if isinstance(userinfo.get("data"), dict) else userinfo
    sub = str(raw.get("sub") or raw.get("id") or raw.get("user_id") or raw.get("username") or "").strip()
    username = str(raw.get("preferred_username") or raw.get("username") or raw.get("name") or raw.get("nickname") or sub).strip()
    nickname = str(raw.get("nickname") or raw.get("name") or username).strip()
    if not sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OnAuth 用户信息缺少唯一标识")
    return {"sub": sub, "username": username, "nickname": nickname}
