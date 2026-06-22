from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import HTTPException, status

from backend.app.core.config import Settings
from backend.app.db.database import execute, query
from backend.app.services.common import build_customer_row, normalize_numeric_amount
from backend.app.services.settings import build_node_display_name
from backend.app.services.logs import write_activity_log
from backend.app.services.subscriptions import build_public_subscription_links, is_local_subscription_enabled, local_subscription_config
from backend.app.services.three_x_ui import (
    ThreeXUIError,
    attach_remote_client,
    bytes_to_gb,
    create_remote_client,
    delete_remote_client,
    detach_remote_client,
    expiry_ms_from_date,
    expiry_text_from_ms,
    extend_expiry_ms,
    format_traffic_text,
    gb_to_bytes,
    get_remote_client,
    get_remote_sub_links,
    is_unlimited_expiry,
    list_node_inbounds,
    list_remote_clients,
    normalize_base_path,
    reset_remote_client_traffic,
    update_remote_client,
)

DEFAULT_MANAGER = "未分配"
DEFAULT_RENEW_PRICE = "未设置"
DEFAULT_TRAFFIC_MULTIPLIER = 1.0
MAX_TRAFFIC_MULTIPLIER = 100.0
AUDIT_ACTION_CREATE = "新增"
AUDIT_ACTION_UPDATE = "修改"
AUDIT_ACTION_DELETE = "删除"
AUDIT_ACTION_RENEW = "续费"
AUDIT_ACTION_RESET_TRAFFIC = "重置流量"
REMOTE_CLIENT_ALLOWED_FIELDS = {
    "email",
    "enable",
    "expiryTime",
    "totalGB",
    "comment",
    "subId",
    "tgId",
    "limitIp",
    "uuid",
    "password",
    "flow",
    "security",
    "method",
    "account",
    "auth",
    "reset",
    "reverse",
    "allowInsecure",
}


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_owner_username(owner_username: str | None) -> str:
    return (owner_username or "").strip()


def _normalize_renew_price_text(price_text: str | None) -> str:
    clean_text = (price_text or "").strip()
    if not clean_text:
        return DEFAULT_RENEW_PRICE
    if clean_text == DEFAULT_RENEW_PRICE:
        return clean_text
    if clean_text.replace(".", "", 1).isdigit():
        return f"{clean_text}/月"
    return clean_text


def _normalize_webhook_url(value: str | None) -> str:
    webhook_url = (value or "").strip()
    if webhook_url and not webhook_url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook 地址必须以 http:// 或 https:// 开头")
    return webhook_url


def _normalize_traffic_multiplier(value: Any) -> float:
    if value in (None, ""):
        return DEFAULT_TRAFFIC_MULTIPLIER
    try:
        multiplier = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="流量倍率格式不正确") from exc
    if multiplier < DEFAULT_TRAFFIC_MULTIPLIER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="流量倍率不能小于 1")
    if multiplier > MAX_TRAFFIC_MULTIPLIER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"流量倍率不能超过 {MAX_TRAFFIC_MULTIPLIER:g}")
    return round(multiplier, 4)


def _profile_traffic_multiplier(profile: Dict[str, Any] | None) -> float:
    try:
        multiplier = float((profile or {}).get("traffic_multiplier") or DEFAULT_TRAFFIC_MULTIPLIER)
    except (TypeError, ValueError):
        multiplier = DEFAULT_TRAFFIC_MULTIPLIER
    return multiplier if multiplier > 0 else DEFAULT_TRAFFIC_MULTIPLIER


def _business_gb_to_remote_bytes(total_gb: int | float | None, multiplier: float) -> int:
    if total_gb is None:
        return 0
    return gb_to_bytes(float(total_gb) / max(multiplier, DEFAULT_TRAFFIC_MULTIPLIER))


def _remote_bytes_to_business_bytes(value: int | float | None, multiplier: float) -> int:
    if value is None:
        return 0
    return int(round(float(value) * max(multiplier, DEFAULT_TRAFFIC_MULTIPLIER)))


def _is_admin_role(role: str | None) -> bool:
    return (role or "").strip().lower() == "admin"


def _display_name_for_user(user: Dict[str, Any]) -> str:
    return ((user.get("nickname") or user.get("username") or "")).strip()


def _find_enabled_user_by_manager(settings: Settings, manager: str) -> Dict[str, Any] | None:
    clean_manager = (manager or "").strip()
    if not clean_manager or clean_manager == DEFAULT_MANAGER:
        return None
    rows = query(
        settings,
        """
        SELECT id, username, nickname
        FROM users
        WHERE COALESCE(enabled, 1) = 1
          AND (username = ? OR nickname = ?)
        ORDER BY CASE WHEN username = ? THEN 0 ELSE 1 END, id ASC
        LIMIT 1
        """,
        (clean_manager, clean_manager, clean_manager),
    )
    return rows[0] if rows else None


def _resolve_owner_username_for_manager(settings: Settings, manager: str, fallback: str = "") -> str:
    user = _find_enabled_user_by_manager(settings, manager)
    if user:
        return _normalize_owner_username(user.get("username"))
    return _normalize_owner_username(fallback)


def _actor_manager_names(settings: Settings, actor: str) -> set[str]:
    clean_actor = _normalize_owner_username(actor)
    if not clean_actor:
        return set()
    names = {clean_actor}
    rows = query(
        settings,
        "SELECT username, nickname FROM users WHERE username = ? AND COALESCE(enabled, 1) = 1 LIMIT 1",
        (clean_actor,),
    )
    if rows:
        display_name = _display_name_for_user(rows[0])
        if display_name:
            names.add(display_name)
    return names


def _can_access_manager(settings: Settings, manager: str, actor: str) -> bool:
    clean_manager = (manager or "").strip()
    return bool(clean_manager) and clean_manager in _actor_manager_names(settings, actor)


def _manager_filter_aliases(settings: Settings, manager: str) -> set[str]:
    clean_manager = (manager or "").strip()
    if not clean_manager:
        return set()
    aliases = {clean_manager}
    user = _find_enabled_user_by_manager(settings, clean_manager)
    if user:
        username = _normalize_owner_username(user.get("username"))
        display_name = _display_name_for_user(user)
        if username:
            aliases.add(username)
        if display_name:
            aliases.add(display_name)
    return aliases


def _generate_remote_email(name: str, owner_username: str = "") -> str:
    name_seed = "".join(ch.lower() if ch.isalnum() else "-" for ch in (name or "").strip())[:24].strip("-")
    owner_seed = "".join(ch.lower() if ch.isalnum() else "-" for ch in (owner_username or "").strip())[:16].strip("-")
    unique_seed = uuid4().hex[:12]
    prefix_parts = [part for part in [name_seed or "client", owner_seed] if part]
    prefix = "-".join(prefix_parts)[:48].strip("-") or "client"
    return f"{prefix}-{unique_seed}@subsentry.local"

def _resolve_expiry_date_text(payload: Dict[str, Any], fallback: str = "") -> str:
    duration_mode = str(payload.get("duration_mode") or "").strip().lower()
    custom_expiry_date = (payload.get("custom_expiry_date") or "").strip()
    direct_expiry_date = (payload.get("expiry_date") or "").strip()

    if duration_mode == "date":
        return custom_expiry_date or direct_expiry_date

    if duration_mode == "days":
        raw_days = payload.get("duration_days")
        if raw_days in (None, ""):
            return fallback
        try:
            duration_days = int(raw_days)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="???????") from exc
        if duration_days == 0:
            return ""
        target_date = datetime.now().date() + timedelta(days=duration_days)
        return target_date.strftime("%Y-%m-%d")

    return custom_expiry_date or direct_expiry_date or fallback



def _load_nodes(settings: Settings) -> Dict[int, Dict[str, Any]]:
    rows = query(settings, "SELECT * FROM catalog_nodes ORDER BY id ASC")
    return {int(row["id"]): row for row in rows}


def _require_node(settings: Settings, node_id: int) -> Dict[str, Any]:
    rows = query(settings, "SELECT * FROM catalog_nodes WHERE id = ?", (node_id,))
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在")
    return rows[0]


def _split_customer_id(customer_id: str) -> tuple[int, str]:
    try:
        node_id_raw, remote_email = str(customer_id).split(":", 1)
        node_id = int(node_id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="客户标识格式无效") from exc
    remote_email = remote_email.strip()
    if not remote_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="客户标识格式无效")
    return node_id, remote_email


def _get_profile(settings: Settings, node_id: int, remote_email: str) -> Dict[str, Any] | None:
    rows = query(
        settings,
        "SELECT * FROM remote_customer_profiles WHERE node_id = ? AND remote_email = ?",
        (node_id, remote_email),
    )
    return rows[0] if rows else None


def _upsert_profile(
    settings: Settings,
    *,
    node_id: int,
    node_name: str,
    remote_email: str,
    display_name: str,
    owner_username: str = "",
    manager: str,
    renew_price: str,
    traffic_multiplier: float = DEFAULT_TRAFFIC_MULTIPLIER,
    webhook_url: str,
    notes: str | None = None,
) -> None:
    existing = _get_profile(settings, node_id, remote_email)
    now_text = _now_text()
    owner_username = _normalize_owner_username(owner_username)
    traffic_multiplier = _normalize_traffic_multiplier(traffic_multiplier)
    clean_notes = str(notes if notes is not None else (existing or {}).get("notes") or "").strip()
    if existing:
        execute(
            settings,
            """
            UPDATE remote_customer_profiles
            SET node_name = ?, display_name = ?, owner_username = ?, manager = ?, renew_price = ?, traffic_multiplier = ?, webhook_url = ?, notes = ?, updated_at = ?
            WHERE node_id = ? AND remote_email = ?
            """,
            (node_name, display_name, owner_username, manager, renew_price, traffic_multiplier, webhook_url, clean_notes, now_text, node_id, remote_email),
        )
        return

    execute(
        settings,
        """
        INSERT INTO remote_customer_profiles
        (node_id, node_name, remote_email, display_name, owner_username, manager, renew_price, traffic_multiplier, webhook_url, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (node_id, node_name, remote_email, display_name, owner_username, manager, renew_price, traffic_multiplier, webhook_url, clean_notes, now_text, now_text),
    )


def _remote_expiry_display(expiry_ms: int | None) -> str:
    return "无限期" if is_unlimited_expiry(expiry_ms) else (expiry_text_from_ms(expiry_ms) or "-")


def _erp_display_name(profile: Dict[str, Any] | None, remote_client: Dict[str, Any], remote_email: str) -> str:
    return ((profile or {}).get("display_name") or remote_client.get("comment") or remote_email).strip()


def _can_access_profile(settings: Settings, profile: Dict[str, Any] | None, actor: str, actor_role: str = "user") -> bool:
    if _is_admin_role(actor_role):
        return True
    owner_username = _normalize_owner_username((profile or {}).get("owner_username"))
    if owner_username and owner_username == _normalize_owner_username(actor):
        return True
    return _can_access_manager(settings, (profile or {}).get("manager") or "", actor)


def _require_customer_access(settings: Settings, profile: Dict[str, Any] | None, actor: str, actor_role: str = "user") -> None:
    if _can_access_profile(settings, profile, actor, actor_role):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this customer")


def _build_traffic_snapshot(remote_client: Dict[str, Any], multiplier: float = DEFAULT_TRAFFIC_MULTIPLIER) -> Dict[str, Any]:
    remote_total_bytes = int(remote_client.get("totalGB") or 0)
    traffic = remote_client.get("traffic") or {}

    try:
        up_bytes = max(int(traffic.get("up") or 0), 0)
    except (TypeError, ValueError):
        up_bytes = 0

    try:
        down_bytes = max(int(traffic.get("down") or 0), 0)
    except (TypeError, ValueError):
        down_bytes = 0

    remote_used_bytes = up_bytes + down_bytes
    is_unlimited_traffic = remote_total_bytes <= 0
    remote_remaining_bytes = None if is_unlimited_traffic else max(remote_total_bytes - remote_used_bytes, 0)
    total_bytes = _remote_bytes_to_business_bytes(remote_total_bytes, multiplier)
    used_bytes = _remote_bytes_to_business_bytes(remote_used_bytes, multiplier)
    remaining_bytes = None if remote_remaining_bytes is None else _remote_bytes_to_business_bytes(remote_remaining_bytes, multiplier)

    return {
        "is_unlimited_traffic": is_unlimited_traffic,
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "remaining_bytes": remaining_bytes,
        "traffic_total_gb": bytes_to_gb(total_bytes),
        "traffic_used_gb": bytes_to_gb(used_bytes),
        "traffic_remaining_gb": None if remaining_bytes is None else bytes_to_gb(remaining_bytes),
        "traffic_total_display": format_traffic_text(total_bytes),
        "traffic_used_display": format_traffic_text(used_bytes),
        "traffic_remaining_display": "Unlimited" if is_unlimited_traffic else format_traffic_text(remaining_bytes),
        "remote_total_bytes": remote_total_bytes,
        "remote_used_bytes": remote_used_bytes,
        "remote_remaining_bytes": remote_remaining_bytes,
    }


def _build_unified_customer(node: Dict[str, Any], remote_client: Dict[str, Any], profile: Dict[str, Any] | None) -> Dict[str, Any]:
    remote_email = (remote_client.get("email") or "").strip()
    sub_id = (remote_client.get("subId") or "").strip()
    display_name = _erp_display_name(profile, remote_client, remote_email)
    manager = ((profile or {}).get("manager") or DEFAULT_MANAGER).strip() or DEFAULT_MANAGER
    owner_username = _normalize_owner_username((profile or {}).get("owner_username"))
    renew_price = ((profile or {}).get("renew_price") or DEFAULT_RENEW_PRICE).strip() or DEFAULT_RENEW_PRICE
    traffic_multiplier = _profile_traffic_multiplier(profile)
    webhook_url = ((profile or {}).get("webhook_url") or "").strip()
    notes = ((profile or {}).get("notes") or "").strip()
    inbound_ids = [int(x) for x in (remote_client.get("inboundIds") or [])]
    inbound_text = ", ".join(str(x) for x in inbound_ids) if inbound_ids else "-"
    expiry_ms = remote_client.get("expiryTime")
    unlimited_expiry = is_unlimited_expiry(expiry_ms)
    expiry_date = expiry_text_from_ms(expiry_ms)
    expiry_display = _remote_expiry_display(expiry_ms)
    traffic_snapshot = _build_traffic_snapshot(remote_client, traffic_multiplier)
    total_bytes = traffic_snapshot["total_bytes"]

    record = {
        "id": f"{node['id']}:{remote_email}",
        "node_id": int(node["id"]),
        "remote_email": remote_email,
        "sub_id": sub_id,
        "name": display_name,
        "manager": manager,
        "owner_username": owner_username,
        "node": build_node_display_name(node.get("name") or "", node.get("address") or ""),
        "node_name": node.get("name") or "",
        "renew_price": renew_price,
        "traffic_multiplier": traffic_multiplier,
        "expiry_date": expiry_date,
        "expiry_display": expiry_display,
        "is_unlimited_expiry": unlimited_expiry,
        "duration": f"Inbounds: {inbound_text}",
        "traffic": traffic_snapshot["traffic_remaining_display"],
        "webhook_url": webhook_url,
        "notes": notes,
        "enable": bool(remote_client.get("enable", True)),
        "inbound_ids": inbound_ids,
        "total_gb": traffic_snapshot["traffic_total_gb"],
        "total_bytes": total_bytes,
        "remote_total_bytes": traffic_snapshot["remote_total_bytes"],
        "used_bytes": traffic_snapshot["used_bytes"],
        "remote_used_bytes": traffic_snapshot["remote_used_bytes"],
        "remaining_bytes": traffic_snapshot["remaining_bytes"],
        "remote_remaining_bytes": traffic_snapshot["remote_remaining_bytes"],
        "traffic_total_gb": traffic_snapshot["traffic_total_gb"],
        "traffic_used_gb": traffic_snapshot["traffic_used_gb"],
        "traffic_remaining_gb": traffic_snapshot["traffic_remaining_gb"],
        "traffic_total_display": traffic_snapshot["traffic_total_display"],
        "traffic_used_display": traffic_snapshot["traffic_used_display"],
        "traffic_remaining_display": traffic_snapshot["traffic_remaining_display"],
        "is_unlimited_traffic": traffic_snapshot["is_unlimited_traffic"],
        "limit_ip": int(remote_client.get("limitIp") or 0),
        "last_online": remote_client.get("lastOnline"),
        "created_at": remote_client.get("createdAt"),
        "updated_at": remote_client.get("updatedAt"),
        "raw_client": remote_client,
    }

    return build_customer_row(record) | {
        "node_id": record["node_id"],
        "node_name": record["node_name"],
        "remote_email": record["remote_email"],
        "sub_id": record["sub_id"],
        "owner_username": record["owner_username"],
        "traffic_multiplier": record["traffic_multiplier"],
        "traffic": record["traffic"],
        "enable": record["enable"],
        "expiry_display": record["expiry_display"],
        "is_unlimited_expiry": record["is_unlimited_expiry"],
        "inbound_ids": record["inbound_ids"],
        "total_gb": record["total_gb"],
        "total_bytes": record["total_bytes"],
        "remote_total_bytes": record["remote_total_bytes"],
        "used_bytes": record["used_bytes"],
        "remote_used_bytes": record["remote_used_bytes"],
        "remaining_bytes": record["remaining_bytes"],
        "remote_remaining_bytes": record["remote_remaining_bytes"],
        "traffic_total_gb": record["traffic_total_gb"],
        "traffic_used_gb": record["traffic_used_gb"],
        "traffic_remaining_gb": record["traffic_remaining_gb"],
        "traffic_total_display": record["traffic_total_display"],
        "traffic_used_display": record["traffic_used_display"],
        "traffic_remaining_display": record["traffic_remaining_display"],
        "is_unlimited_traffic": record["is_unlimited_traffic"],
        "limit_ip": record["limit_ip"],
        "webhook_url": record["webhook_url"],
        "notes": record["notes"],
        "last_online": record["last_online"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "raw_client": record["raw_client"],
    }


def _safe_remote_detail(node: Dict[str, Any], remote_email: str) -> Dict[str, Any]:
    try:
        return get_remote_client(node, remote_email)
    except ThreeXUIError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _remote_detail_with_traffic(node: Dict[str, Any], remote_email: str) -> Dict[str, Any]:
    remote_detail = _safe_remote_detail(node, remote_email)
    if remote_detail.get("traffic"):
        return remote_detail

    try:
        remote_rows = list_remote_clients(node)
    except ThreeXUIError:
        return remote_detail

    for row in remote_rows:
        if (row.get("email") or "").strip() != remote_email:
            continue
        enriched = dict(remote_detail)
        for key in ("traffic", "lastOnline", "createdAt", "updatedAt"):
            if key in row and key not in enriched:
                enriched[key] = row.get(key)
        return enriched

    return remote_detail


def _sanitize_remote_client_payload(remote_client: Dict[str, Any]) -> Dict[str, Any]:
    sanitized: Dict[str, Any] = {}
    for key in REMOTE_CLIENT_ALLOWED_FIELDS:
        if key in remote_client:
            sanitized[key] = remote_client.get(key)
    return sanitized


def _append_audit_changes(summary_parts: List[str], old_data: Dict[str, Any], new_data: Dict[str, Any]) -> None:
    audit_keys = {
        "name": "客户名称",
        "manager": "客户经理",
        "node": "所属节点",
        "expiry_display": "到期时间",
        "renew_price": "续费价格",
        "traffic_multiplier": "流量倍率",
        "traffic_used_display": "已用流量",
        "traffic_remaining_display": "剩余流量",
        "webhook_url": "Webhook",
        "notes": "备注",
        "enable": "启用状态",
        "sub_id": "3X-UI 订阅ID",
        "inbound_ids": "挂载入站",
    }
    for key, label in audit_keys.items():
        old_val = old_data.get(key)
        new_val = new_data.get(key)
        if key == "enable":
            old_val = "启用" if old_val not in (False, 0, "0") else "停用"
            new_val = "启用" if new_val not in (False, 0, "0") else "停用"
        if key == "inbound_ids":
            old_val = ", ".join(str(x) for x in (old_val or [])) or "-"
            new_val = ", ".join(str(x) for x in (new_val or [])) or "-"
        if (old_val or "") != (new_val or ""):
            summary_parts.append(f"{label}: {old_val or '-'} -> {new_val or '-'}")


def write_customer_audit(
    settings: Settings,
    customer_id: str,
    customer_name: str,
    actor: str,
    action: str,
    old_data: Dict[str, Any],
    new_data: Dict[str, Any],
) -> None:
    summary_parts: List[str] = []
    if action == AUDIT_ACTION_CREATE:
        summary_parts.append(f"新增客户：{customer_name}")
    elif action == AUDIT_ACTION_DELETE:
        summary_parts.append(f"删除客户：{customer_name}")
    elif action == AUDIT_ACTION_RENEW:
        summary_parts.append(f"续费客户：{customer_name}")
    elif action == AUDIT_ACTION_RESET_TRAFFIC:
        summary_parts.append(f"重置客户流量：{customer_name}")
    else:
        summary_parts.append(f"修改客户：{customer_name}")

    if action not in (AUDIT_ACTION_CREATE, AUDIT_ACTION_DELETE):
        _append_audit_changes(summary_parts, old_data, new_data)

    node_id = int(new_data.get("node_id") or old_data.get("node_id") or 0) or None
    remote_email = new_data.get("remote_email") or old_data.get("remote_email")
    execute(
        settings,
        """
        INSERT INTO customer_audit_logs (customer_id, node_id, remote_email, customer_name, action, actor, change_summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (0, node_id, remote_email, customer_name, action, actor, "；".join(summary_parts), _now_text()),
    )


def _sort_customers(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows.sort(
        key=lambda item: (
            0 if item.get("status_level") == "expired" else
            1 if item.get("status_level") == "today" else
            2 if item.get("status_level") == "warning" else
            3 if item.get("status_level") == "disabled" else
            4 if item.get("status_level") == "unlimited" else
            5,
            item.get("remaining_days", 999999),
            item.get("name", ""),
        )
    )
    return rows


def _node_customer_rows(node: Dict[str, Any], profile_map: Dict[tuple[int, str], Dict[str, Any]]) -> List[Dict[str, Any]]:
    remote_clients = list_remote_clients(node)
    rows: List[Dict[str, Any]] = []
    for remote_client in remote_clients:
        remote_email = (remote_client.get("email") or "").strip()
        rows.append(_build_unified_customer(node, remote_client, profile_map.get((int(node["id"]), remote_email))))
    return rows


def list_customers(
    settings: Settings,
    keyword: str = "",
    node_filter: str = "",
    node_id_filter: int | None = None,
    manager_filter: str = "",
    *,
    actor: str = "",
    actor_role: str = "admin",
) -> List[Dict[str, Any]]:
    keyword = (keyword or "").strip().lower()
    node_filter = (node_filter or "").strip()
    node_id_filter = int(node_id_filter or 0)
    manager_filter = (manager_filter or "").strip()

    nodes = list(_load_nodes(settings).values())
    profiles = query(settings, "SELECT * FROM remote_customer_profiles")
    profile_map = {(int(item["node_id"]), item["remote_email"]): item for item in profiles}
    result: List[Dict[str, Any]] = []

    if not nodes:
        return result

    max_workers = min(max(len(nodes), 1), 8)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_node_customer_rows, node, profile_map): node for node in nodes}
        for future in as_completed(future_map):
            try:
                result.extend(future.result())
            except Exception:
                continue

    filtered: List[Dict[str, Any]] = []
    actor_username = _normalize_owner_username(actor)
    actor_manager_names = _actor_manager_names(settings, actor)
    manager_filter_aliases = _manager_filter_aliases(settings, manager_filter)
    for row in result:
        if not _is_admin_role(actor_role):
            owner_matches = _normalize_owner_username(row.get("owner_username")) == actor_username
            manager_matches = (row.get("manager") or "").strip() in actor_manager_names
            if not owner_matches and not manager_matches:
                continue
        if keyword:
            haystacks = [
                (row.get("name") or "").lower(),
                (row.get("remote_email") or "").lower(),
                (row.get("sub_id") or "").lower(),
                (row.get("node") or "").lower(),
                (row.get("manager") or "").lower(),
                (row.get("owner_username") or "").lower(),
            ]
            if not any(keyword in text for text in haystacks):
                continue
        if node_id_filter and int(row.get("node_id") or 0) != node_id_filter:
            continue
        if not node_id_filter and node_filter and row.get("node") != node_filter:
            continue
        if manager_filter and (row.get("manager") or "").strip() not in manager_filter_aliases and _normalize_owner_username(row.get("owner_username")) not in manager_filter_aliases:
            continue
        filtered.append(row)

    return _sort_customers(filtered)


def get_customer(settings: Settings, customer_id: str, *, actor: str = "", actor_role: str = "admin") -> Dict[str, Any]:
    node_id, remote_email = _split_customer_id(customer_id)
    node = _require_node(settings, node_id)
    remote_client = _remote_detail_with_traffic(node, remote_email)
    profile = _get_profile(settings, node_id, remote_email)
    _require_customer_access(settings, profile, actor, actor_role)
    row = _build_unified_customer(node, remote_client, profile)
    row["inbounds"] = list_node_inbounds(node)
    return row


def _build_remote_update_payload(current_remote: Dict[str, Any], payload: Dict[str, Any], current_view: Dict[str, Any], remote_email: str) -> Dict[str, Any]:
    new_email = (payload.get("remote_email") or remote_email).strip()
    current_multiplier = _normalize_traffic_multiplier(current_view.get("traffic_multiplier"))
    target_multiplier = _normalize_traffic_multiplier(payload.get("traffic_multiplier") if "traffic_multiplier" in payload else current_multiplier)
    remote_payload = _sanitize_remote_client_payload(current_remote)
    remote_payload["email"] = new_email
    remote_payload["comment"] = (payload.get("name") or current_view["name"]).strip()
    if any(key in payload for key in {"expiry_date", "custom_expiry_date", "duration_mode", "duration_days"}):
        remote_payload["expiryTime"] = expiry_ms_from_date(_resolve_expiry_date_text(payload, current_view.get("expiry_date", "")))
    if "total_gb" in payload or "traffic_multiplier" in payload:
        business_total_gb = payload.get("total_gb") if "total_gb" in payload else current_view.get("traffic_total_gb")
        remote_payload["totalGB"] = _business_gb_to_remote_bytes(business_total_gb, target_multiplier)
    if "enable" in payload:
        remote_payload["enable"] = bool(payload.get("enable"))
    if "limit_ip" in payload:
        remote_payload["limitIp"] = int(payload.get("limit_ip") or 0)
    return remote_payload


def _sync_inbound_attachments(node: Dict[str, Any], remote_email: str, old_inbound_ids: List[int], new_inbound_ids: List[int]) -> None:
    old_set = {int(x) for x in old_inbound_ids}
    new_set = {int(x) for x in new_inbound_ids}
    to_attach = sorted(new_set - old_set)
    to_detach = sorted(old_set - new_set)
    if to_attach:
        attach_remote_client(node, remote_email, to_attach)
    if to_detach:
        detach_remote_client(node, remote_email, to_detach)


def _prepare_create_payload(settings: Settings, payload: Dict[str, Any]) -> tuple[Dict[str, Any], List[int], Dict[str, Any]]:
    name = (payload.get("name") or "").strip()
    manager = (payload.get("manager") or DEFAULT_MANAGER).strip() or DEFAULT_MANAGER
    owner_username = _normalize_owner_username(
        payload.get("owner_username") or payload.get("actor") or _resolve_owner_username_for_manager(settings, manager)
    )
    remote_email = (payload.get("remote_email") or payload.get("email") or "").strip()
    if not remote_email:
        remote_email = _generate_remote_email(name, owner_username)
    renew_price = _normalize_renew_price_text(payload.get("renew_price"))
    traffic_multiplier = _normalize_traffic_multiplier(payload.get("traffic_multiplier"))
    webhook_url = _normalize_webhook_url(payload.get("webhook_url"))
    notes = (payload.get("notes") or "").strip()
    node_id = payload.get("node_id")
    inbound_ids = [int(x) for x in (payload.get("inbound_ids") or [])]
    total_gb = payload.get("total_gb")
    expiry_date = _resolve_expiry_date_text(payload)

    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="????????")
    if not node_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="?????")
    if not inbound_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="????????")

    node = _require_node(settings, int(node_id))
    client_payload = {
        "email": remote_email,
        "comment": name,
        "totalGB": _business_gb_to_remote_bytes(total_gb, traffic_multiplier),
        "expiryTime": expiry_ms_from_date(expiry_date),
        "enable": bool(payload.get("enable", True)),
        "limitIp": int(payload.get("limit_ip") or 0),
        "tgId": int(payload.get("tg_id") or 0),
    }
    profile_payload = {
        "display_name": name,
        "manager": manager,
        "renew_price": renew_price,
        "traffic_multiplier": traffic_multiplier,
        "webhook_url": webhook_url,
        "notes": notes,
    }
    return client_payload, inbound_ids, {"node": node, "profile": profile_payload}


def create_customer(settings: Settings, payload: Dict[str, Any], actor: str, actor_role: str = "admin") -> Dict[str, Any]:
    if not _is_admin_role(actor_role):
        payload = {
            **payload,
            "manager": actor,
            "owner_username": actor,
        }
    client_payload, inbound_ids, extra = _prepare_create_payload(settings, payload)
    node = extra["node"]
    profile_payload = extra["profile"]
    if _is_admin_role(actor_role):
        owner_username = _normalize_owner_username(
            payload.get("owner_username")
            or _resolve_owner_username_for_manager(settings, profile_payload["manager"])
            or actor
        )
    else:
        owner_username = _normalize_owner_username(actor)
    try:
        create_remote_client(node, client_payload, inbound_ids)
    except ThreeXUIError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _upsert_profile(
        settings,
        node_id=int(node["id"]),
        node_name=node["name"],
        remote_email=client_payload["email"],
        display_name=profile_payload["display_name"],
        owner_username=owner_username,
        manager=profile_payload["manager"],
        renew_price=profile_payload["renew_price"],
        traffic_multiplier=profile_payload["traffic_multiplier"],
        webhook_url=profile_payload["webhook_url"],
    )

    amount = normalize_numeric_amount(profile_payload["renew_price"])
    if amount is not None:
        execute(
            settings,
            """
            INSERT INTO financial_logs (customer_id, owner_username, node_id, remote_email, customer_name, renew_price, amount, renew_days, new_expiry, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                0,
                owner_username,
                node["id"],
                client_payload["email"],
                profile_payload["display_name"],
                profile_payload["renew_price"],
                amount,
                0,
                _remote_expiry_display(client_payload["expiryTime"]),
                _now_text(),
            ),
        )

    write_customer_audit(
        settings,
        f"{node['id']}:{client_payload['email']}",
        profile_payload["display_name"],
        actor,
        AUDIT_ACTION_CREATE,
        {},
        {
            "name": profile_payload["display_name"],
            "manager": profile_payload["manager"],
            "node": node["name"],
            "node_id": node["id"],
            "remote_email": client_payload["email"],
            "owner_username": owner_username,
            "expiry_display": _remote_expiry_display(client_payload["expiryTime"]),
            "renew_price": profile_payload["renew_price"],
            "webhook_url": profile_payload["webhook_url"],
            "enable": client_payload["enable"],
            "inbound_ids": inbound_ids,
        },
    )
    return {
        "success": True,
        "message": f"客户 [{profile_payload['display_name']}] 创建成功",
        "customer_id": f"{node['id']}:{client_payload['email']}",
    }


def update_customer(settings: Settings, customer_id: str, payload: Dict[str, Any], actor: str = "admin", actor_role: str = "admin") -> Dict[str, Any]:
    node_id, remote_email = _split_customer_id(customer_id)
    node = _require_node(settings, node_id)
    remote_detail = _safe_remote_detail(node, remote_email)
    profile = _get_profile(settings, node_id, remote_email)
    _require_customer_access(settings, profile, actor, actor_role)
    current_view = _build_unified_customer(node, remote_detail, profile)

    display_name = (payload.get("name") or current_view["name"]).strip()
    manager = (payload.get("manager") or current_view["manager"]).strip() or DEFAULT_MANAGER
    if not _is_admin_role(actor_role):
        manager = current_view["manager"] or _normalize_owner_username(actor) or DEFAULT_MANAGER
    renew_price = _normalize_renew_price_text(payload.get("renew_price") if "renew_price" in payload else current_view["renew_price"])
    traffic_multiplier = _normalize_traffic_multiplier(payload.get("traffic_multiplier") if "traffic_multiplier" in payload else current_view.get("traffic_multiplier"))
    webhook_url = _normalize_webhook_url(payload.get("webhook_url") if "webhook_url" in payload else current_view.get("webhook_url"))
    notes = (payload.get("notes") if "notes" in payload else current_view.get("notes") or "")
    notes = str(notes or "").strip()
    new_email = (payload.get("remote_email") or remote_email).strip()
    new_inbound_ids = [int(x) for x in payload.get("inbound_ids", current_view.get("inbound_ids", []))]

    if not display_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="客户名称不能为空")
    if not new_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="3X-UI 客户邮箱标识不能为空")
    if not new_inbound_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一个入站")

    remote_fields = {"name", "remote_email", "expiry_date", "custom_expiry_date", "duration_mode", "duration_days", "total_gb", "traffic_multiplier", "enable", "limit_ip"}
    inbound_changed = "inbound_ids" in payload
    remote_changed = any(key in payload for key in remote_fields)

    if remote_changed:
        remote_payload = _build_remote_update_payload(remote_detail, payload, current_view, remote_email)
        try:
            update_remote_client(node, remote_email, remote_payload)
        except ThreeXUIError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    else:
        remote_payload = dict(remote_detail)

    target_email = (remote_payload.get("email") or new_email).strip()
    if inbound_changed:
        try:
            _sync_inbound_attachments(node, target_email, current_view.get("inbound_ids", []), new_inbound_ids)
        except ThreeXUIError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    current_owner_username = _normalize_owner_username(current_view.get("owner_username") or actor)
    owner_username = current_owner_username
    if _is_admin_role(actor_role):
        owner_username = _resolve_owner_username_for_manager(settings, manager, current_owner_username)

    _upsert_profile(
        settings,
        node_id=node_id,
        node_name=node["name"],
        remote_email=target_email,
        display_name=display_name,
        owner_username=owner_username,
        manager=manager,
        renew_price=renew_price,
        traffic_multiplier=traffic_multiplier,
        webhook_url=webhook_url,
        notes=notes,
    )
    if target_email != remote_email:
        execute(settings, "DELETE FROM remote_customer_profiles WHERE node_id = ? AND remote_email = ?", (node_id, remote_email))

    refreshed_remote = _safe_remote_detail(node, target_email)
    updated_view = _build_unified_customer(node, refreshed_remote, _get_profile(settings, node_id, target_email))
    write_customer_audit(
        settings,
        customer_id,
        updated_view["name"],
        actor,
        AUDIT_ACTION_UPDATE,
        {
            "name": current_view["name"],
            "manager": current_view["manager"],
            "node": current_view["node"],
            "node_id": current_view["node_id"],
            "remote_email": current_view["remote_email"],
            "sub_id": current_view.get("sub_id", ""),
            "expiry_display": current_view.get("expiry_display", current_view["expiry_date"]),
            "renew_price": current_view["renew_price"],
            "traffic_multiplier": current_view.get("traffic_multiplier", DEFAULT_TRAFFIC_MULTIPLIER),
            "webhook_url": current_view.get("webhook_url", ""),
            "notes": current_view.get("notes", ""),
            "enable": current_view.get("enable", True),
            "inbound_ids": current_view.get("inbound_ids", []),
        },
        {
            "name": updated_view["name"],
            "manager": updated_view["manager"],
            "node": updated_view["node"],
            "node_id": updated_view["node_id"],
            "remote_email": updated_view["remote_email"],
            "sub_id": updated_view.get("sub_id", ""),
            "expiry_display": updated_view.get("expiry_display", updated_view["expiry_date"]),
            "renew_price": updated_view["renew_price"],
            "traffic_multiplier": updated_view.get("traffic_multiplier", DEFAULT_TRAFFIC_MULTIPLIER),
            "webhook_url": updated_view.get("webhook_url", ""),
            "notes": updated_view.get("notes", ""),
            "enable": updated_view.get("enable", True),
            "inbound_ids": updated_view.get("inbound_ids", []),
        },
    )
    return {"success": True, "message": "客户资料已更新"}


def reset_customer_traffic(settings: Settings, customer_id: str, actor: str = "admin", actor_role: str = "admin") -> Dict[str, Any]:
    node_id, remote_email = _split_customer_id(customer_id)
    node = _require_node(settings, node_id)
    remote_detail = _remote_detail_with_traffic(node, remote_email)
    profile = _get_profile(settings, node_id, remote_email)
    _require_customer_access(settings, profile, actor, actor_role)
    current_view = _build_unified_customer(node, remote_detail, profile)

    try:
        reset_remote_client_traffic(node, remote_email)
    except ThreeXUIError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    refreshed_remote = _remote_detail_with_traffic(node, remote_email)
    updated_view = _build_unified_customer(node, refreshed_remote, profile)
    write_customer_audit(
        settings,
        customer_id,
        updated_view["name"],
        actor,
        AUDIT_ACTION_RESET_TRAFFIC,
        {
            "name": current_view["name"],
            "node_id": node_id,
            "remote_email": remote_email,
            "traffic_used_display": current_view.get("traffic_used_display"),
            "traffic_remaining_display": current_view.get("traffic_remaining_display"),
        },
        {
            "name": updated_view["name"],
            "node_id": node_id,
            "remote_email": remote_email,
            "traffic_used_display": updated_view.get("traffic_used_display"),
            "traffic_remaining_display": updated_view.get("traffic_remaining_display"),
        },
    )
    return {"success": True, "message": f"客户 [{updated_view['name']}] 流量已重置", "data": updated_view}


def delete_customer(settings: Settings, customer_id: str, actor: str, actor_role: str = "admin") -> Dict[str, Any]:
    node_id, remote_email = _split_customer_id(customer_id)
    node = _require_node(settings, node_id)
    remote_detail = _safe_remote_detail(node, remote_email)
    profile = _get_profile(settings, node_id, remote_email)
    _require_customer_access(settings, profile, actor, actor_role)
    current_view = _build_unified_customer(node, remote_detail, profile)

    try:
        delete_remote_client(node, remote_email, keep_traffic=False)
    except ThreeXUIError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    execute(settings, "DELETE FROM remote_customer_profiles WHERE node_id = ? AND remote_email = ?", (node_id, remote_email))
    write_customer_audit(
        settings,
        customer_id,
        current_view["name"],
        actor,
        AUDIT_ACTION_DELETE,
        {
            "name": current_view["name"],
            "manager": current_view["manager"],
            "node": current_view["node"],
            "node_id": current_view["node_id"],
            "remote_email": current_view["remote_email"],
            "sub_id": current_view.get("sub_id", ""),
            "expiry_display": current_view.get("expiry_display", current_view["expiry_date"]),
            "renew_price": current_view["renew_price"],
            "webhook_url": current_view.get("webhook_url", ""),
            "enable": current_view.get("enable", True),
            "inbound_ids": current_view.get("inbound_ids", []),
        },
        {},
    )
    return {"success": True, "message": "客户已删除"}


def customer_audit_logs(settings: Settings, customer_id: str, *, action: str = "", actor: str = "", actor_role: str = "admin") -> List[Dict[str, Any]]:
    node_id, remote_email = _split_customer_id(customer_id)
    profile = _get_profile(settings, node_id, remote_email)
    _require_customer_access(settings, profile, actor, actor_role)
    conditions = ["node_id = ?", "remote_email = ?"]
    params: List[Any] = [node_id, remote_email]
    if action:
        conditions.append("action = ?")
        params.append(action)
    return query(
        settings,
        f"""
        SELECT id, customer_name, action, actor, change_summary, created_at
        FROM customer_audit_logs
        WHERE {" AND ".join(conditions)}
        ORDER BY id DESC
        LIMIT 20
        """,
        tuple(params),
    )

def process_customer_renew(settings: Settings, customer_id: str, days_to_add: int, new_price: str, actor: str, actor_role: str = "admin", reset_traffic: bool = False) -> Dict[str, Any]:
    node_id, remote_email = _split_customer_id(customer_id)
    node = _require_node(settings, node_id)
    remote_detail = _safe_remote_detail(node, remote_email)
    profile = _get_profile(settings, node_id, remote_email)
    _require_customer_access(settings, profile, actor, actor_role)
    current_view = _build_unified_customer(node, remote_detail, profile)

    try:
        days_to_add = int(days_to_add)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="续期天数格式不正确") from exc

    new_expiry_ms = extend_expiry_ms(remote_detail.get("expiryTime"), days_to_add)
    remote_payload = _sanitize_remote_client_payload(remote_detail)
    remote_payload["expiryTime"] = new_expiry_ms
    enable_after_renew = True if current_view.get("enable") is False else current_view.get("enable", True)
    if current_view.get("enable") is False:
        remote_payload["enable"] = True

    try:
        update_remote_client(node, remote_email, remote_payload)
    except ThreeXUIError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    final_price = _normalize_renew_price_text(new_price or current_view["renew_price"])
    owner_username = _resolve_owner_username_for_manager(
        settings,
        current_view["manager"],
        _normalize_owner_username(current_view.get("owner_username") or actor),
    )
    _upsert_profile(
        settings,
        node_id=node_id,
        node_name=node["name"],
        remote_email=remote_email,
        display_name=current_view["name"],
        owner_username=owner_username,
        manager=current_view["manager"],
        renew_price=final_price,
        traffic_multiplier=current_view.get("traffic_multiplier") or DEFAULT_TRAFFIC_MULTIPLIER,
        webhook_url=current_view.get("webhook_url", ""),
    )

    new_expiry_display = _remote_expiry_display(new_expiry_ms)
    amount = normalize_numeric_amount(final_price)
    execute(
        settings,
        """
        INSERT INTO financial_logs (customer_id, owner_username, node_id, remote_email, customer_name, renew_price, amount, renew_days, new_expiry, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (0, owner_username, node_id, remote_email, current_view["name"], final_price, amount, days_to_add, new_expiry_display, _now_text()),
    )
    execute(
        settings,
        """
        INSERT INTO customer_renewal_logs (customer_id, node_id, remote_email, customer_name, actor, renew_days, old_expiry, new_expiry, renew_price, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            0,
            node_id,
            remote_email,
            current_view["name"],
            actor,
            days_to_add,
            current_view.get("expiry_display", current_view["expiry_date"]),
            new_expiry_display,
            final_price,
            _now_text(),
        ),
    )
    write_customer_audit(
        settings,
        customer_id,
        current_view["name"],
        actor,
        AUDIT_ACTION_RENEW,
        {
            "name": current_view["name"],
            "manager": current_view["manager"],
            "node": current_view["node"],
            "node_id": node_id,
            "remote_email": remote_email,
            "sub_id": current_view.get("sub_id", ""),
            "expiry_display": current_view.get("expiry_display", current_view["expiry_date"]),
            "renew_price": current_view["renew_price"],
            "webhook_url": current_view.get("webhook_url", ""),
            "enable": current_view.get("enable", True),
            "inbound_ids": current_view.get("inbound_ids", []),
        },
        {
            "name": current_view["name"],
            "manager": current_view["manager"],
            "node": current_view["node"],
            "node_id": node_id,
            "remote_email": remote_email,
            "sub_id": current_view.get("sub_id", ""),
            "expiry_display": new_expiry_display,
            "renew_price": final_price,
            "webhook_url": current_view.get("webhook_url", ""),
            "enable": enable_after_renew,
            "inbound_ids": current_view.get("inbound_ids", []),
        },
    )
    reset_result = reset_customer_traffic(settings, customer_id, actor=actor, actor_role=actor_role) if reset_traffic else None
    return {
        "success": True,
        "message": f"客户 [{current_view['name']}] 续期成功，新到期时间：{new_expiry_display}",
        "new_expiry": new_expiry_display,
        "renew_price": final_price,
        "reset_traffic": bool(reset_traffic),
        "reset_traffic_message": (reset_result or {}).get("message", ""),
    }


def customer_renewal_logs(settings: Settings, customer_id: str, *, actor: str = "", actor_role: str = "admin") -> List[Dict[str, Any]]:
    node_id, remote_email = _split_customer_id(customer_id)
    profile = _get_profile(settings, node_id, remote_email)
    _require_customer_access(settings, profile, actor, actor_role)
    return query(
        settings,
        """
        SELECT id, customer_name, actor, renew_days, old_expiry, new_expiry, renew_price, created_at
        FROM customer_renewal_logs
        WHERE node_id = ? AND remote_email = ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (node_id, remote_email),
    )


def _public_node_origin(node: Dict[str, Any]) -> str:
    scheme = (node.get("subscription_scheme") or node.get("scheme") or "https").strip().lower()
    address = (node.get("subscription_address") or node.get("address") or "").strip()
    port = int(node.get("subscription_port") or 10882)
    if not address or port <= 0:
        return ""
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    return f"{scheme}://{address}" if default_port else f"{scheme}://{address}:{port}"


def _subscription_paths(node: Dict[str, Any], sub_id: str) -> Dict[str, str]:
    origin = _public_node_origin(node)
    if not origin or not sub_id:
        return {"standard": "", "json": "", "clash": ""}
    sub_path = normalize_base_path(node.get("subscription_sub_path") or "/sub")
    json_path = normalize_base_path(node.get("subscription_json_path") or "/json")
    clash_path = normalize_base_path(node.get("subscription_clash_path") or "/clash")
    return {
        "standard": f"{origin}{sub_path}/{sub_id}",
        "json": f"{origin}{json_path}/{sub_id}",
        "clash": f"{origin}{clash_path}/{sub_id}",
    }


def get_customer_subscription(settings: Settings, customer_id: str, *, actor: str = "", actor_role: str = "admin") -> Dict[str, Any]:
    node_id, remote_email = _split_customer_id(customer_id)
    node = _require_node(settings, node_id)
    remote_detail = _remote_detail_with_traffic(node, remote_email)
    profile = _get_profile(settings, node_id, remote_email)
    _require_customer_access(settings, profile, actor, actor_role)
    customer = _build_unified_customer(node, remote_detail, profile)
    sub_id = (customer.get("sub_id") or "").strip()
    remote_links = _subscription_paths(node, sub_id)
    local_links = build_public_subscription_links(settings, node, sub_id)
    local_enabled = is_local_subscription_enabled(settings)
    links = local_links if local_enabled else remote_links
    protocol_links: List[str] = []
    if sub_id:
        try:
            protocol_links = get_remote_sub_links(node, sub_id)
        except ThreeXUIError:
            protocol_links = []
    return {
        "success": True,
        "data": {
            "customer_id": customer["id"],
            "name": customer["name"],
            "node": customer["node"],
            "sub_id": sub_id,
            "links": links,
            "remote_links": remote_links,
            "local_links": local_links,
            "local_subscription": local_subscription_config(settings),
            "protocol_links": protocol_links,
        },
    }


def _bulk_result(total: int, updated: List[Dict[str, Any]], errors: List[Dict[str, str]]) -> Dict[str, Any]:
    return {
        "success": not errors,
        "message": f"已处理 {len(updated)}/{total} 个客户" + (f"，失败 {len(errors)} 个" if errors else ""),
        "total": total,
        "updated": updated,
        "errors": errors,
    }


def _require_bulk_customer_ids(customer_ids: List[str]) -> List[str]:
    cleaned = [str(item).strip() for item in (customer_ids or []) if str(item or "").strip()]
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择至少一个客户")
    return cleaned


def bulk_assign_manager(settings: Settings, customer_ids: List[str], manager: str, actor: str, actor_role: str = "admin") -> Dict[str, Any]:
    clean_manager = (manager or DEFAULT_MANAGER).strip() or DEFAULT_MANAGER
    ids = _require_bulk_customer_ids(customer_ids)
    updated: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for customer_id in ids:
        try:
            result = update_customer(settings, customer_id, {"manager": clean_manager}, actor=actor, actor_role=actor_role)
            updated.append({"id": customer_id, "message": result.get("message", "ok")})
        except Exception as exc:
            errors.append({"id": customer_id, "message": str(exc)})

    result = _bulk_result(len(ids), updated, errors)
    write_activity_log(
        settings,
        category="bulk",
        action="assign_manager",
        actor=actor,
        target_type="customer",
        status="partial" if errors else "success",
        summary=f"批量分配客户经理：{len(updated)}/{len(ids)}",
        detail={"manager": clean_manager, "updated": updated, "errors": errors},
    )
    return result


def bulk_update_customer_fields(
    settings: Settings,
    customer_ids: List[str],
    payload: Dict[str, Any],
    actor: str,
    actor_role: str = "admin",
) -> Dict[str, Any]:
    ids = _require_bulk_customer_ids(customer_ids)
    allowed_keys = {"enable", "total_gb", "traffic_multiplier", "duration_mode", "duration_days", "custom_expiry_date", "expiry_date", "limit_ip", "renew_price"}
    clean_payload = {key: value for key, value in payload.items() if key in allowed_keys}
    if not clean_payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少可批量更新的字段")

    updated: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    for customer_id in ids:
        try:
            result = update_customer(settings, customer_id, clean_payload, actor=actor, actor_role=actor_role)
            updated.append({"id": customer_id, "message": result.get("message", "ok")})
        except Exception as exc:
            errors.append({"id": customer_id, "message": str(exc)})

    result = _bulk_result(len(ids), updated, errors)
    write_activity_log(
        settings,
        category="bulk",
        action="update_customer_fields",
        actor=actor,
        target_type="customer",
        status="partial" if errors else "success",
        summary=f"批量更新客户：{len(updated)}/{len(ids)}",
        detail={"payload": clean_payload, "updated": updated, "errors": errors},
    )
    return result
