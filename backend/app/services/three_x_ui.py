import math
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import requests

from backend.app.core.config import load_settings
from backend.app.services.url_guard import UnsafeUrlError, validate_outbound_url


class ThreeXUIError(Exception):
    pass


def normalize_base_path(base_path: str | None) -> str:
    value = (base_path or "/").strip() or "/"
    if not value.startswith("/"):
        value = f"/{value}"
    return value.rstrip("/") or "/"


def build_panel_base_url(node: Dict[str, Any]) -> str:
    scheme = (node.get("scheme") or "https").strip().lower()
    address = (node.get("address") or "").strip()
    port = int(node.get("port") or 0)
    base_path = normalize_base_path(node.get("base_path"))
    if not address or port <= 0:
        raise ThreeXUIError("Node connection settings are incomplete")
    return f"{scheme}://{address}:{port}{base_path}".rstrip("/")


def _extract_payload(data: Any) -> Any:
    if isinstance(data, dict):
        if "obj" in data:
            return data.get("obj")
        if "data" in data:
            return data.get("data")
    return data


def request_panel(
    node: Dict[str, Any],
    method: str,
    path: str,
    *,
    params: Dict[str, Any] | None = None,
    json_body: Any = None,
    timeout: int = 12,
) -> Any:
    url = f"{build_panel_base_url(node)}{path}"
    try:
        url = validate_outbound_url(load_settings(), url, label="Node panel URL")
    except UnsafeUrlError as exc:
        raise ThreeXUIError(str(exc)) from exc
    headers = {
        "Accept": "application/json",
    }
    api_token = (node.get("api_token") or "").strip()
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=timeout,
            verify=not bool(node.get("allow_insecure")),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ThreeXUIError(f"Failed to connect to panel: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise ThreeXUIError(f"Panel returned non-JSON response ({response.status_code})") from exc

    if response.status_code >= 400:
        message = data.get("msg") if isinstance(data, dict) else ""
        raise ThreeXUIError(message or f"Panel request failed with HTTP {response.status_code}")

    if isinstance(data, dict) and data.get("success") is False:
        raise ThreeXUIError(data.get("msg") or "Panel returned an unsuccessful response")

    return _extract_payload(data)


def test_panel_connection(node: Dict[str, Any]) -> Dict[str, Any]:
    started_at = time.perf_counter()
    status_obj = request_panel(node, "GET", "/panel/api/server/status")
    measured_latency_ms = max(int(round((time.perf_counter() - started_at) * 1000)), 1)
    inbounds = request_panel(node, "GET", "/panel/api/inbounds/options")

    reported_latency_ms = 0
    if isinstance(status_obj, dict):
        try:
            reported_latency_ms = int(status_obj.get("latencyMs") or 0)
        except (TypeError, ValueError):
            reported_latency_ms = 0

    return {
        "status": "online",
        "latency_ms": reported_latency_ms or measured_latency_ms,
        "panel_version": status_obj.get("panelVersion", "") if isinstance(status_obj, dict) else "",
        "xray_version": status_obj.get("xrayVersion", "") if isinstance(status_obj, dict) else "",
        "inbound_count": len(inbounds or []),
        "server_status": status_obj or {},
    }


def get_panel_settings(node: Dict[str, Any]) -> Dict[str, Any]:
    data = request_panel(node, "POST", "/panel/setting/all")
    return data if isinstance(data, dict) else {}


def list_node_inbounds(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = request_panel(node, "GET", "/panel/api/inbounds/options")
    result: List[Dict[str, Any]] = []
    for item in rows or []:
        result.append(
            {
                "id": item.get("id"),
                "remark": item.get("remark") or f"Inbound-{item.get('id')}",
                "protocol": item.get("protocol") or "",
                "port": item.get("port"),
                "tls_flow_capable": bool(item.get("tlsFlowCapable")),
            }
        )
    return result


def list_remote_clients(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = request_panel(node, "GET", "/panel/api/clients/list")
    return [normalize_remote_client_payload(item) for item in list(rows or [])]


def get_remote_client(node: Dict[str, Any], email: str) -> Dict[str, Any]:
    row = request_panel(node, "GET", f"/panel/api/clients/get/{email}")
    if not isinstance(row, dict):
        raise ThreeXUIError("Panel returned invalid client details")
    return normalize_remote_client_payload(row)


def get_remote_sub_links(node: Dict[str, Any], sub_id: str) -> List[str]:
    if not (sub_id or "").strip():
        return []
    rows = request_panel(node, "GET", f"/panel/api/clients/subLinks/{sub_id}")
    if not isinstance(rows, list):
        return []
    return [str(item) for item in rows if str(item or "").strip()]


def get_last_online_map(node: Dict[str, Any]) -> Dict[str, Any]:
    data = request_panel(node, "POST", "/panel/api/inbounds/lastOnline")
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        result: Dict[str, Any] = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            last_online = item.get("lastOnline") or item.get("last_online")
            for key_name in ("subId", "email", "id", "uuid", "clientId"):
                key = str(item.get(key_name) or "").strip()
                if key and last_online:
                    result[key] = last_online
        return result
    return {}


def normalize_remote_client_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    client = payload.get("client")
    if isinstance(client, dict):
        merged = dict(client)
        for key in (
            "inboundIds",
            "enable",
            "expiryTime",
            "totalGB",
            "comment",
            "traffic",
            "lastOnline",
            "last_online",
            "createdAt",
            "updatedAt",
        ):
            if key in payload and key not in merged:
                merged[key] = payload.get(key)
        return merged

    return payload


def create_remote_client(node: Dict[str, Any], client_payload: Dict[str, Any], inbound_ids: List[int]) -> None:
    request_panel(
        node,
        "POST",
        "/panel/api/clients/add",
        json_body={"client": client_payload, "inboundIds": inbound_ids},
    )


def update_remote_client(node: Dict[str, Any], email: str, client_payload: Dict[str, Any]) -> None:
    request_panel(
        node,
        "POST",
        f"/panel/api/clients/update/{email}",
        json_body=client_payload,
    )


def attach_remote_client(node: Dict[str, Any], email: str, inbound_ids: List[int]) -> None:
    if not inbound_ids:
        return
    request_panel(
        node,
        "POST",
        f"/panel/api/clients/{email}/attach",
        json_body={"inboundIds": inbound_ids},
    )


def detach_remote_client(node: Dict[str, Any], email: str, inbound_ids: List[int]) -> None:
    if not inbound_ids:
        return
    request_panel(
        node,
        "POST",
        f"/panel/api/clients/{email}/detach",
        json_body={"inboundIds": inbound_ids},
    )


def delete_remote_client(node: Dict[str, Any], email: str, keep_traffic: bool = False) -> None:
    request_panel(
        node,
        "POST",
        f"/panel/api/clients/del/{email}",
        params={"keepTraffic": 1 if keep_traffic else 0},
    )


def reset_remote_client_traffic(node: Dict[str, Any], email: str) -> None:
    request_panel(
        node,
        "POST",
        f"/panel/api/clients/resetTraffic/{email}",
    )


def parse_expiry_date(value: str | None) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    return datetime.strptime(raw, "%Y-%m-%d")


def is_unlimited_expiry(expiry_ms: int | None) -> bool:
    return not expiry_ms or int(expiry_ms) <= 0


def expiry_text_from_ms(expiry_ms: int | None) -> str:
    if is_unlimited_expiry(expiry_ms):
        return ""
    return datetime.fromtimestamp(int(expiry_ms) / 1000).strftime("%Y-%m-%d")


def expiry_ms_from_date(date_text: str | None) -> int:
    if not date_text:
        return 0
    dt = parse_expiry_date(date_text)
    if dt is None:
        return 0
    return int(dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)


def extend_expiry_ms(current_expiry_ms: int | None, days_to_add: int) -> int:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if not is_unlimited_expiry(current_expiry_ms):
        current_dt = datetime.fromtimestamp(int(current_expiry_ms) / 1000).replace(hour=0, minute=0, second=0, microsecond=0)
        start_dt = current_dt if current_dt >= today else today
    else:
        start_dt = today
    return int((start_dt + timedelta(days=days_to_add)).timestamp() * 1000)


def gb_to_bytes(total_gb: int | float | None) -> int:
    if total_gb is None:
        return 0
    try:
        value = float(total_gb)
    except (TypeError, ValueError):
        return 0
    if value <= 0:
        return 0
    return int(value * 1024 * 1024 * 1024)


def bytes_to_gb(total_bytes: int | float | None) -> float:
    if not total_bytes:
        return 0.0
    return round(float(total_bytes) / 1024 / 1024 / 1024, 2)


def format_traffic_text(total_bytes: int | float | None) -> str:
    total_gb = bytes_to_gb(total_bytes)
    if total_gb <= 0:
        return "Unlimited"
    if math.isclose(total_gb, round(total_gb)):
        return f"{int(round(total_gb))} GB"
    return f"{total_gb} GB"
