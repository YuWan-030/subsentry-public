import base64
import html
import json
from typing import Any, Dict, List
from urllib.parse import quote, unquote, urlparse

import requests
from fastapi import HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, Response

from backend.app.core.config import Settings
from backend.app.db.database import get_setting, query
from backend.app.services.common import get_bool_setting
from backend.app.services.settings import build_node_display_name
from backend.app.services.three_x_ui import ThreeXUIError, get_last_online_map, get_remote_sub_links, list_remote_clients, normalize_base_path

LOCAL_SUBSCRIPTION_ENABLED_KEY = "local_subscription_enabled"
LOCAL_SUBSCRIPTION_BASE_URL_KEY = "local_subscription_base_url"
LOCAL_SUBSCRIPTION_PORT_KEY = "local_subscription_port"
LOCAL_SUBSCRIPTION_TITLE_KEY = "local_subscription_title"


def is_local_subscription_enabled(settings: Settings) -> bool:
    return get_bool_setting(settings, LOCAL_SUBSCRIPTION_ENABLED_KEY, False)


def _public_origin(settings: Settings) -> str:
    configured_url = (get_setting(settings, LOCAL_SUBSCRIPTION_BASE_URL_KEY, settings.public_subscription_base_url) or "").strip().rstrip("/")
    if configured_url:
        return configured_url
    return f"http://127.0.0.1:{local_subscription_port(settings)}"


def local_subscription_port(settings: Settings) -> int:
    try:
        return int(get_setting(settings, LOCAL_SUBSCRIPTION_PORT_KEY, "10883") or 10883)
    except (TypeError, ValueError):
        return 10883


def local_subscription_title(settings: Settings) -> str:
    return (get_setting(settings, LOCAL_SUBSCRIPTION_TITLE_KEY, "SubSentry") or "SubSentry").strip()


def local_subscription_config(settings: Settings) -> Dict[str, Any]:
    return {
        "enabled": is_local_subscription_enabled(settings),
        "base_url": _public_origin(settings),
        "port": local_subscription_port(settings),
        "title": local_subscription_title(settings),
    }


def build_public_subscription_links(settings: Settings, node: Dict[str, Any], sub_id: str) -> Dict[str, str]:
    clean_sub_id = (sub_id or "").strip()
    if not clean_sub_id or not is_local_subscription_enabled(settings):
        return {"standard": "", "json": "", "clash": ""}
    origin = _public_origin(settings)
    node_id = int(node.get("id") or 0)
    return {
        "standard": f"{origin}/sub/{node_id}/{quote(clean_sub_id, safe='')}",
        "json": f"{origin}/json/{node_id}/{quote(clean_sub_id, safe='')}",
        "clash": f"{origin}/clash/{node_id}/{quote(clean_sub_id, safe='')}",
    }


def _require_node(settings: Settings, node_id: int) -> Dict[str, Any]:
    rows = query(settings, "SELECT * FROM catalog_nodes WHERE id = ?", (node_id,))
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Node not found")
    return rows[0]


def _profile_for_remote_email(settings: Settings, node_id: int, remote_email: str) -> Dict[str, Any] | None:
    rows = query(
        settings,
        "SELECT * FROM remote_customer_profiles WHERE node_id = ? AND remote_email = ?",
        (node_id, remote_email),
    )
    return rows[0] if rows else None


def _remote_client_for_sub_id(node: Dict[str, Any], sub_id: str) -> Dict[str, Any]:
    try:
        rows = list_remote_clients(node)
    except ThreeXUIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    clean_sub_id = (sub_id or "").strip()
    for row in rows:
        if (row.get("subId") or "").strip() == clean_sub_id:
            if row.get("enable") is False:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription is disabled")
            return row
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")


def _has_last_online(remote_client: Dict[str, Any]) -> bool:
    return any(remote_client.get(key) not in (None, "", 0, "0") for key in ("lastOnline", "last_online", "last_online_at"))


def _enrich_last_online(node: Dict[str, Any], remote_client: Dict[str, Any]) -> Dict[str, Any]:
    if _has_last_online(remote_client):
        return remote_client

    try:
        last_online_map = get_last_online_map(node)
    except ThreeXUIError:
        return remote_client

    normalized_map = {str(key).strip().lower(): value for key, value in last_online_map.items()}
    lookup_keys = [
        remote_client.get("subId"),
        remote_client.get("email"),
        remote_client.get("id"),
        remote_client.get("uuid"),
        remote_client.get("clientId"),
    ]
    for key in lookup_keys:
        clean_key = str(key or "").strip()
        if clean_key and last_online_map.get(clean_key) not in (None, "", 0, "0"):
            enriched = dict(remote_client)
            enriched["lastOnline"] = last_online_map.get(clean_key)
            return enriched
        lower_key = clean_key.lower()
        if lower_key and normalized_map.get(lower_key) not in (None, "", 0, "0"):
            enriched = dict(remote_client)
            enriched["lastOnline"] = normalized_map.get(lower_key)
            return enriched

    return remote_client


def _subscription_title(settings: Settings, node: Dict[str, Any], profile: Dict[str, Any] | None, remote_client: Dict[str, Any], sub_id: str) -> str:
    return (
        local_subscription_title(settings)
        or
        (profile or {}).get("display_name")
        or remote_client.get("comment")
        or build_node_display_name(node.get("name") or "", node.get("address") or "")
        or sub_id
        or "SubSentry"
    ).strip()


def _traffic_multiplier(profile: Dict[str, Any] | None) -> float:
    try:
        multiplier = float((profile or {}).get("traffic_multiplier") or 1)
    except (TypeError, ValueError):
        multiplier = 1
    return multiplier if multiplier > 0 else 1


def _scale_traffic_value(value: int | float | None, multiplier: float) -> int:
    if value is None:
        return 0
    return int(round(float(value) * multiplier))


def _traffic_header(remote_client: Dict[str, Any], profile: Dict[str, Any] | None = None) -> str:
    multiplier = _traffic_multiplier(profile)
    traffic = remote_client.get("traffic") or {}
    try:
        upload = _scale_traffic_value(max(int(traffic.get("up") or 0), 0), multiplier)
    except (TypeError, ValueError):
        upload = 0
    try:
        download = _scale_traffic_value(max(int(traffic.get("down") or 0), 0), multiplier)
    except (TypeError, ValueError):
        download = 0
    try:
        total = _scale_traffic_value(max(int(remote_client.get("totalGB") or 0), 0), multiplier)
    except (TypeError, ValueError):
        total = 0
    try:
        expiry_ms = int(remote_client.get("expiryTime") or 0)
    except (TypeError, ValueError):
        expiry_ms = 0
    expire = int(expiry_ms / 1000) if expiry_ms > 0 else 0
    return f"upload={upload}; download={download}; total={total}; expire={expire}"


def _traffic_snapshot(remote_client: Dict[str, Any], profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    multiplier = _traffic_multiplier(profile)
    traffic = remote_client.get("traffic") or {}
    try:
        upload = _scale_traffic_value(max(int(traffic.get("up") or 0), 0), multiplier)
    except (TypeError, ValueError):
        upload = 0
    try:
        download = _scale_traffic_value(max(int(traffic.get("down") or 0), 0), multiplier)
    except (TypeError, ValueError):
        download = 0
    try:
        total = _scale_traffic_value(max(int(remote_client.get("totalGB") or 0), 0), multiplier)
    except (TypeError, ValueError):
        total = 0
    used = upload + download
    percent = 0 if total <= 0 else min(round(used / total * 100, 1), 100)
    return {
        "upload": upload,
        "download": download,
        "used": used,
        "total": total,
        "remaining": None if total <= 0 else max(total - used, 0),
        "percent": percent,
    }


def _format_bytes(value: int | float | None) -> str:
    if value is None:
        return "∞"
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "0 B"
    if size <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}" if size < 10 and index > 0 else f"{size:.1f} {units[index]}"


def _expiry_text(remote_client: Dict[str, Any]) -> str:
    try:
        expiry_ms = int(remote_client.get("expiryTime") or 0)
    except (TypeError, ValueError):
        expiry_ms = 0
    if expiry_ms <= 0:
        return "无到期"
    from datetime import datetime

    return datetime.fromtimestamp(expiry_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _last_online_text(remote_client: Dict[str, Any]) -> str:
    value = remote_client.get("lastOnline") or remote_client.get("last_online") or remote_client.get("last_online_at")
    if not value:
        return "-"
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return str(value)
    if timestamp > 10_000_000_000:
        timestamp = int(timestamp / 1000)
    from datetime import datetime

    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def _subscription_urls(settings: Settings, node_id: int, sub_id: str) -> Dict[str, str]:
    clean_sub_id = quote((sub_id or "").strip(), safe="")
    origin = _public_origin(settings)
    return {
        "standard": f"{origin}/sub/{node_id}/{clean_sub_id}?raw=1",
        "page": f"{origin}/sub/{node_id}/{clean_sub_id}",
        "json": f"{origin}/json/{node_id}/{clean_sub_id}",
        "clash": f"{origin}/clash/{node_id}/{clean_sub_id}",
    }


def _protocol_label(url: str) -> Dict[str, str]:
    parsed = urlparse(url)
    protocol = (parsed.scheme or "link").upper()
    name = unquote(parsed.fragment or parsed.netloc or parsed.path or protocol)
    return {"protocol": protocol, "name": name}


def _json_script_data(data: Dict[str, Any]) -> str:
    return html.escape(json.dumps(data, ensure_ascii=False), quote=False)


def _link_row(tag: str, name: str, url: str) -> str:
    safe_tag = html.escape(tag, quote=True)
    safe_name = html.escape(name, quote=True)
    safe_url = html.escape(url, quote=True)
    return (
        f'<div class="row">'
        f'<span class="tag">{safe_tag}</span>'
        f'<span class="row-name">{safe_name}</span>'
        f'<span class="actions">'
        f'<button class="small" onclick="copyText(\'{safe_url}\')" title="复制">⧉</button>'
        f'<a class="small" href="{safe_url}" title="打开" style="display:grid;place-items:center">↗</a>'
        f'</span>'
        f'</div>'
    )


def _protocol_row(protocol: str, name: str, url: str) -> str:
    safe_protocol = html.escape(protocol, quote=True)
    safe_name = html.escape(name, quote=True)
    safe_url = html.escape(url, quote=True)
    return (
        f'<div class="row">'
        f'<span class="tag">{safe_protocol}</span>'
        f'<span class="row-name">{safe_name}</span>'
        f'<span class="actions">'
        f'<button class="small" onclick="copyText(\'{safe_url}\')" title="复制">⧉</button>'
        f'</span>'
        f'</div>'
    )


def _common_headers(title: str, remote_client: Dict[str, Any], filename_ext: str, profile: Dict[str, Any] | None = None) -> Dict[str, str]:
    encoded_title = quote(title)
    base64_title = base64.b64encode(title.encode("utf-8")).decode("ascii")
    return {
        "profile-title": f"base64:{base64_title}",
        "Profile-Title": f"base64:{base64_title}",
        "profile-title-legacy": encoded_title,
        "profile-name": encoded_title,
        "subscription-title": encoded_title,
        "subscription-userinfo": _traffic_header(remote_client, profile),
        "profile-update-interval": "24",
        "Cache-Control": "no-store",
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_title}.{filename_ext}",
    }


def _subscription_metadata_lines(title: str) -> List[str]:
    base64_title = base64.b64encode(title.encode("utf-8")).decode("ascii")
    return [
        f"#profile-title: base64:{base64_title}",
        f"#profile-title-legacy: {title}",
        f"#subscription-title: {title}",
        f"#remark: {title}",
        f"#remarks: {title}",
        f"#name: {title}",
    ]


def _load_context(settings: Settings, node_id: int, sub_id: str) -> Dict[str, Any]:
    if not is_local_subscription_enabled(settings):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local subscription service is disabled")
    node = _require_node(settings, node_id)
    remote_client = _enrich_last_online(node, _remote_client_for_sub_id(node, sub_id))
    remote_email = (remote_client.get("email") or "").strip()
    profile = _profile_for_remote_email(settings, node_id, remote_email) if remote_email else None
    return {
        "node": node,
        "remote_client": remote_client,
        "profile": profile,
        "title": _subscription_title(settings, node, profile, remote_client, sub_id),
    }


def _remote_subscription_origin(node: Dict[str, Any]) -> str:
    scheme = (node.get("subscription_scheme") or node.get("scheme") or "https").strip().lower()
    address = (node.get("subscription_address") or node.get("address") or "").strip()
    try:
        port = int(node.get("subscription_port") or 10882)
    except (TypeError, ValueError):
        port = 10882
    if not address or port <= 0:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Node subscription settings are incomplete")
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    return f"{scheme}://{address}" if default_port else f"{scheme}://{address}:{port}"


def _remote_subscription_url(node: Dict[str, Any], kind: str, sub_id: str) -> str:
    path_key = {
        "json": "subscription_json_path",
        "clash": "subscription_clash_path",
    }[kind]
    default_path = "/json" if kind == "json" else "/clash"
    path = normalize_base_path(node.get(path_key) or default_path)
    return f"{_remote_subscription_origin(node)}{path}/{quote((sub_id or '').strip(), safe='')}"


def _fetch_remote_subscription(node: Dict[str, Any], kind: str, sub_id: str) -> requests.Response:
    try:
        response = requests.get(
            _remote_subscription_url(node, kind, sub_id),
            headers={"Accept": "application/json" if kind == "json" else "text/yaml, text/plain, */*"},
            timeout=12,
            verify=not bool(node.get("allow_insecure")),
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to fetch remote subscription: {exc}") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Remote subscription returned HTTP {response.status_code}")
    return response


def _protocol_links(node: Dict[str, Any], sub_id: str) -> List[str]:
    try:
        links = get_remote_sub_links(node, sub_id)
    except ThreeXUIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return [item.strip() for item in links if item.strip()]


def standard_subscription_response(settings: Settings, node_id: int, sub_id: str) -> Response:
    context = _load_context(settings, node_id, sub_id)
    links = _protocol_links(context["node"], sub_id)
    if not links:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription has no protocol links")
    title = context["title"]
    subscription_text = "\n".join([*_subscription_metadata_lines(title), *links]) + "\n"
    body = base64.b64encode(subscription_text.encode("utf-8")).decode("ascii")
    return Response(
        body,
        media_type="text/plain; charset=utf-8",
        headers=_common_headers(title, context["remote_client"], "txt", context["profile"]),
    )


def subscription_landing_page_response(settings: Settings, node_id: int, sub_id: str) -> HTMLResponse:
    context = _load_context(settings, node_id, sub_id)
    node = context["node"]
    remote_client = context["remote_client"]
    profile = context["profile"] or {}
    title = context["title"]
    links = _protocol_links(node, sub_id)
    urls = _subscription_urls(settings, node_id, sub_id)
    traffic = _traffic_snapshot(remote_client, profile)
    customer_name = (profile.get("display_name") or remote_client.get("comment") or remote_client.get("email") or sub_id or "-").strip()
    node_name = build_node_display_name(node.get("name") or "", node.get("address") or "")
    status_text = "已启用" if remote_client.get("enable") is not False else "已停用"
    quota_text = "无限制" if traffic["total"] <= 0 else _format_bytes(traffic["total"])
    remaining_text = "∞" if traffic["remaining"] is None else _format_bytes(traffic["remaining"])
    protocol_items = [
        {
            "url": item,
            **_protocol_label(item),
        }
        for item in links
    ]
    page_data = {
        "title": title,
        "standardUrl": urls["standard"],
        "pageUrl": urls["page"],
        "jsonUrl": urls["json"],
        "clashUrl": urls["clash"],
    }

    def esc(value: Any) -> str:
        return html.escape(str(value or ""), quote=True)

    subscription_rows = "\n".join(
        [
            _link_row("SUB", "标准订阅", urls["standard"]),
            _link_row("JSON", "JSON 订阅", urls["json"]),
            _link_row("CLASH", "Clash 订阅", urls["clash"]),
        ]
    )
    protocol_rows = "\n".join(
        _protocol_row(item["protocol"], item["name"], item["url"])
        for item in protocol_items
    ) or '<div class="empty">暂无可用协议链接</div>'

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)} · 订阅信息</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: rgba(255,255,255,.82);
      --panel-strong: #ffffff;
      --text: #172033;
      --muted: #667085;
      --line: rgba(35,45,68,.14);
      --brand: #1677ff;
      --brand-2: #19b394;
      --warn: #f59e0b;
      --danger: #ef4444;
      --shadow: 0 22px 70px rgba(33, 45, 77, .14);
    }}
    :root[data-theme="dark"] {{
      --bg: #15171d;
      --panel: rgba(35,38,47,.9);
      --panel-strong: #242833;
      --text: #f3f7ff;
      --muted: #a7b0c2;
      --line: rgba(161,174,201,.18);
      --brand: #4f9cff;
      --brand-2: #49d6b6;
      --warn: #f7b955;
      --danger: #fb7185;
      --shadow: 0 24px 80px rgba(0,0,0,.3);
    }}
    :root[data-theme="sweetpink"] {{
      --bg: #fff7fb;
      --panel: rgba(255,255,255,.86);
      --panel-strong: #fffafd;
      --text: #372232;
      --muted: #8a6479;
      --line: rgba(226,143,176,.25);
      --brand: #e68fb0;
      --brand-2: #84c7b0;
      --warn: #e89b45;
      --danger: #df6f7f;
      --shadow: 0 24px 80px rgba(230,143,176,.22);
    }}
    @media (prefers-color-scheme: dark) {{
      :root:not([data-theme="light"]):not([data-theme="sweetpink"]) {{
        --bg: #15171d;
        --panel: rgba(35,38,47,.9);
        --panel-strong: #242833;
        --text: #f3f7ff;
        --muted: #a7b0c2;
        --line: rgba(161,174,201,.18);
        --brand: #4f9cff;
        --brand-2: #49d6b6;
        --warn: #f7b955;
        --danger: #fb7185;
        --shadow: 0 24px 80px rgba(0,0,0,.3);
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 12% 8%, color-mix(in srgb, var(--brand) 22%, transparent), transparent 32%),
        radial-gradient(circle at 88% 18%, color-mix(in srgb, var(--brand-2) 18%, transparent), transparent 30%),
        linear-gradient(180deg, var(--bg), color-mix(in srgb, var(--bg) 88%, var(--brand) 12%));
      color: var(--text);
    }}
    a {{ color: inherit; text-decoration: none; }}
    .wrap {{ width: min(980px, calc(100vw - 28px)); margin: 28px auto 48px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: var(--shadow); backdrop-filter: blur(18px); overflow: hidden; }}
    .top {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 22px 24px; border-bottom: 1px solid var(--line); }}
    .title h1 {{ font-size: clamp(22px, 4vw, 34px); margin: 0 0 8px; letter-spacing: 0; }}
    .title p {{ margin: 0; color: var(--muted); font-size: 14px; }}
    .toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }}
    .icon-btn, .btn {{ border: 1px solid var(--line); background: var(--panel-strong); color: var(--text); border-radius: 11px; min-height: 38px; padding: 0 13px; cursor: pointer; font-weight: 650; }}
    .icon-btn {{ width: 38px; padding: 0; }}
    .btn.primary {{ background: var(--brand); border-color: color-mix(in srgb, var(--brand) 70%, black); color: white; }}
    .content {{ padding: 22px 24px 26px; }}
    .grid {{ display: grid; grid-template-columns: 1.15fr .85fr; gap: 16px; }}
    .panel {{ background: color-mix(in srgb, var(--panel-strong) 82%, transparent); border: 1px solid var(--line); border-radius: 14px; padding: 16px; }}
    .info-table {{ width: 100%; border-collapse: collapse; overflow: hidden; border-radius: 12px; }}
    .info-table td {{ border-bottom: 1px solid var(--line); padding: 12px 14px; font-size: 14px; }}
    .info-table tr:last-child td {{ border-bottom: 0; }}
    .info-table td:first-child {{ color: var(--muted); width: 32%; }}
    .pill {{ display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 4px 9px; font-size: 12px; font-weight: 700; background: color-mix(in srgb, var(--brand) 14%, transparent); color: var(--brand); }}
    .usage-number {{ font-size: 32px; font-weight: 800; margin: 0; }}
    .usage-meta {{ margin: 8px 0 16px; color: var(--muted); }}
    .bar {{ height: 11px; background: color-mix(in srgb, var(--muted) 16%, transparent); border-radius: 999px; overflow: hidden; }}
    .bar span {{ display: block; height: 100%; width: {traffic["percent"]}%; background: linear-gradient(90deg, var(--brand), var(--brand-2)); }}
    .stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 14px; }}
    .stat {{ border: 1px solid var(--line); border-radius: 12px; padding: 10px; }}
    .stat b {{ display: block; font-size: 15px; margin-bottom: 3px; }}
    .stat span {{ color: var(--muted); font-size: 12px; }}
    .section-title {{ display: flex; align-items: center; gap: 12px; margin: 22px 0 12px; color: var(--muted); font-weight: 800; }}
    .section-title::before, .section-title::after {{ content: ""; height: 1px; flex: 1; background: var(--line); }}
    .row {{ display: grid; grid-template-columns: auto 1fr auto; gap: 10px; align-items: center; border: 1px solid var(--line); background: color-mix(in srgb, var(--panel-strong) 70%, transparent); border-radius: 12px; padding: 10px 11px; margin-bottom: 9px; }}
    .tag {{ font-size: 11px; font-weight: 800; border-radius: 7px; padding: 5px 7px; color: var(--brand); background: color-mix(in srgb, var(--brand) 14%, transparent); }}
    .row-name {{ min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 700; font-size: 13px; }}
    .actions {{ display: flex; gap: 7px; }}
    .small {{ width: 32px; height: 32px; border-radius: 9px; border: 1px solid var(--line); background: transparent; color: var(--text); cursor: pointer; }}
    .import-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-top: 10px; }}
    .import-card {{ border: 1px solid var(--line); background: color-mix(in srgb, var(--panel-strong) 76%, transparent); border-radius: 14px; padding: 14px; }}
    .import-card h3 {{ margin: 0 0 10px; font-size: 15px; }}
    .import-card .btn {{ width: 100%; margin-top: 8px; }}
    .empty {{ color: var(--muted); border: 1px dashed var(--line); padding: 18px; border-radius: 12px; text-align: center; }}
    .toast {{ position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%) translateY(20px); opacity: 0; background: var(--panel-strong); color: var(--text); border: 1px solid var(--line); border-radius: 12px; padding: 10px 14px; box-shadow: var(--shadow); transition: .2s; pointer-events: none; }}
    .toast.show {{ opacity: 1; transform: translateX(-50%) translateY(0); }}
    @media (max-width: 760px) {{
      .wrap {{ width: min(100vw - 18px, 980px); margin-top: 10px; }}
      .top {{ align-items: flex-start; padding: 18px; }}
      .content {{ padding: 16px; }}
      .grid, .import-grid {{ grid-template-columns: 1fr; }}
      .row {{ grid-template-columns: auto minmax(0,1fr); }}
      .actions {{ grid-column: 1 / -1; justify-content: flex-end; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="top">
        <div class="title">
          <h1>{esc(title)}</h1>
          <p>{esc(customer_name)} · {esc(node_name)} · <span class="pill">{esc(status_text)}</span></p>
        </div>
        <div class="toolbar">
          <button class="icon-btn" onclick="setTheme('light')" title="浅色">☀</button>
          <button class="icon-btn" onclick="setTheme('dark')" title="深色">☾</button>
          <button class="icon-btn" onclick="setTheme('sweetpink')" title="甜莓粉">♡</button>
          <button class="btn primary" onclick="copyText(DATA.standardUrl)">复制订阅</button>
        </div>
      </div>
      <div class="content">
        <div class="grid">
          <div class="panel">
            <table class="info-table">
              <tr><td>订阅 ID</td><td>{esc(sub_id)}</td></tr>
              <tr><td>客户</td><td>{esc(customer_name)}</td></tr>
              <tr><td>节点</td><td>{esc(node_name)}</td></tr>
              <tr><td>状态</td><td>{esc(status_text)}</td></tr>
              <tr><td>总额度</td><td>{esc(quota_text)}</td></tr>
              <tr><td>剩余额度</td><td>{esc(remaining_text)}</td></tr>
              <tr><td>上次在线</td><td>{esc(_last_online_text(remote_client))}</td></tr>
              <tr><td>到期</td><td>{esc(_expiry_text(remote_client))}</td></tr>
            </table>
          </div>
          <div class="panel">
            <p class="usage-number">{esc(_format_bytes(traffic["used"]))}</p>
            <p class="usage-meta">已用 / {esc(quota_text)}</p>
            <div class="bar"><span></span></div>
            <div class="stats">
              <div class="stat"><b>{esc(_format_bytes(traffic["download"]))}</b><span>下载</span></div>
              <div class="stat"><b>{esc(_format_bytes(traffic["upload"]))}</b><span>上传</span></div>
              <div class="stat"><b>{esc(remaining_text)}</b><span>剩余</span></div>
              <div class="stat"><b>{esc(str(traffic["percent"]) + "%" if traffic["total"] > 0 else "∞")}</b><span>使用率</span></div>
            </div>
          </div>
        </div>

        <div class="section-title">订阅链接</div>
        {subscription_rows}

        <div class="section-title">一键导入</div>
        <div class="import-grid">
          <div class="import-card">
            <h3>Windows</h3>
            <button class="btn primary" onclick="openImport('windows')">导入 v2rayN</button>
            <button class="btn" onclick="openImport('hiddify')">导入 Hiddify</button>
            <button class="btn" onclick="openImport('hiddifyLegacy')">Hiddify Legacy</button>
            <button class="btn" onclick="openImport('singbox')">导入 sing-box</button>
            <button class="btn" onclick="copyText(DATA.standardUrl)">复制订阅链接</button>
          </div>
          <div class="import-card">
            <h3>Android</h3>
            <button class="btn primary" onclick="openImport('android')">导入 v2rayNG</button>
            <button class="btn" onclick="openImport('hiddify')">导入 Hiddify</button>
            <button class="btn" onclick="openImport('hiddifyLegacy')">Hiddify Legacy</button>
            <button class="btn" onclick="openImport('singbox')">导入 sing-box</button>
            <button class="btn" onclick="copyText(DATA.standardUrl)">复制订阅链接</button>
          </div>
          <div class="import-card">
            <h3>iOS</h3>
            <button class="btn primary" onclick="openImport('shadowrocket')">Shadowrocket</button>
            <button class="btn" onclick="openImport('stash')">Stash</button>
            <button class="btn" onclick="openImport('hiddify')">Hiddify</button>
            <button class="btn" onclick="openImport('hiddifyLegacy')">Hiddify Legacy</button>
            <button class="btn" onclick="openImport('singbox')">sing-box</button>
          </div>
          <div class="import-card">
            <h3>Clash 系</h3>
            <button class="btn primary" onclick="openImport('clash')">Clash / Mihomo</button>
            <button class="btn" onclick="copyText(DATA.clashUrl)">复制 Clash 链接</button>
          </div>
        </div>

        <div class="section-title">协议链接</div>
        {protocol_rows}
      </div>
    </div>
  </div>
  <div id="toast" class="toast">已复制</div>
  <script id="page-data" type="application/json">{_json_script_data(page_data)}</script>
  <script>
    const DATA = JSON.parse(document.getElementById('page-data').textContent);
    const savedTheme = localStorage.getItem('subsentry-sub-theme');
    if (savedTheme) document.documentElement.dataset.theme = savedTheme;
    function setTheme(theme) {{
      document.documentElement.dataset.theme = theme;
      localStorage.setItem('subsentry-sub-theme', theme);
    }}
    function toast(text) {{
      const el = document.getElementById('toast');
      el.textContent = text || '已复制';
      el.classList.add('show');
      setTimeout(() => el.classList.remove('show'), 1500);
    }}
    async function copyText(text) {{
      try {{
        await navigator.clipboard.writeText(text);
        toast('已复制到剪贴板');
      }} catch (e) {{
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        toast('已复制到剪贴板');
      }}
    }}
    function utf8b64(text) {{
      return btoa(unescape(encodeURIComponent(text)));
    }}
    function openImport(kind) {{
      const url = DATA.standardUrl;
      const clash = DATA.clashUrl;
      const title = DATA.title;
      const encodedUrl = encodeURIComponent(url);
      const encodedTitle = encodeURIComponent(title);
      const b64Url = utf8b64(url);
      const targets = {{
        windows: `v2rayn://install-sub?url=${{encodedUrl}}&name=${{encodedTitle}}`,
        android: `v2rayng://install-sub?url=${{encodedUrl}}&name=${{encodedTitle}}`,
        shadowrocket: `shadowrocket://add/sub://${{b64Url}}?remark=${{encodedTitle}}`,
        stash: `stash://install-config?url=${{encodeURIComponent(clash)}}&name=${{encodedTitle}}`,
        hiddify: `hiddify://import/${{encodedUrl}}#${{encodedTitle}}`,
        hiddifyLegacy: `hiddify://install-sub?url=${{encodedUrl}}#${{encodedTitle}}`,
        singbox: `sing-box://import-remote-profile?url=${{encodedUrl}}#${{encodedTitle}}`,
        clash: `clash://install-config?url=${{encodeURIComponent(clash)}}&name=${{encodedTitle}}`
      }};
      window.location.href = targets[kind] || url;
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


def json_subscription_response(settings: Settings, node_id: int, sub_id: str) -> JSONResponse:
    context = _load_context(settings, node_id, sub_id)
    try:
        payload = _fetch_remote_subscription(context["node"], "json", sub_id).json()
    except (HTTPException, ValueError):
        payload = _protocol_links(context["node"], sub_id)

    if isinstance(payload, dict):
        data = dict(payload)
        data.setdefault("title", context["title"])
    elif isinstance(payload, list):
        data = {"title": context["title"], "proxies": payload}
    else:
        data = {"title": context["title"], "proxies": []}

    return JSONResponse(
        data,
        headers=_common_headers(context["title"], context["remote_client"], "json", context["profile"]),
    )


def _yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _with_yaml_title(text: str, title: str) -> str:
    clean_text = (text or "").lstrip()
    title_line = f"title: {_yaml_string(title)}"
    lines = clean_text.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("title:"):
            lines[index] = title_line
            return "\n".join(lines) + "\n"
    return f"{title_line}\n{clean_text}"


def clash_subscription_response(settings: Settings, node_id: int, sub_id: str) -> Response:
    context = _load_context(settings, node_id, sub_id)
    remote_response = _fetch_remote_subscription(context["node"], "clash", sub_id)
    body = _with_yaml_title(remote_response.text, context["title"])
    return Response(
        body,
        media_type="text/yaml; charset=utf-8",
        headers=_common_headers(context["title"], context["remote_client"], "yaml", context["profile"]),
    )
