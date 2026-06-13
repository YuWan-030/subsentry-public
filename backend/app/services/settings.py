from datetime import datetime
from typing import Any, Dict, Tuple

from fastapi import HTTPException, status

from backend.app.core.config import Settings
from backend.app.db.database import execute, get_setting, query
from backend.app.services.common import get_bool_setting, get_int_setting
from backend.app.services.logs import write_activity_log
from backend.app.services.task_state import record_task_state
from backend.app.services.three_x_ui import ThreeXUIError, get_panel_settings, list_node_inbounds, normalize_base_path, test_panel_connection

NODE_ABNORMAL_NOTIFY_FAILURE_THRESHOLD = 3


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_node_display_name(name: str, address: str) -> str:
    clean_name = (name or "").strip()
    clean_address = (address or "").strip()
    if clean_name and clean_address:
        return f"{clean_name}-[{clean_address}]"
    return clean_name or clean_address


def _normalize_path(value: str | None, default: str) -> str:
    raw = (value or default).strip() or default
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return raw.rstrip("/") or default


def _first_setting_value(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data.get(key) not in (None, ""):
            return data.get(key)
    return None


def _subscription_defaults(payload: Dict[str, Any]) -> Dict[str, Any]:
    scheme = (payload.get("subscription_scheme") or payload.get("scheme") or "https").strip().lower()
    if scheme not in ("http", "https"):
        scheme = "https"
    address = (payload.get("subscription_address") or payload.get("address") or "").strip()
    try:
        port = int(payload.get("subscription_port") or 10882)
    except (TypeError, ValueError):
        port = 10882
    return {
        "subscription_scheme": scheme,
        "subscription_address": address,
        "subscription_port": port if port > 0 else 10882,
        "subscription_sub_path": _normalize_path(payload.get("subscription_sub_path"), "/sub"),
        "subscription_json_path": _normalize_path(payload.get("subscription_json_path"), "/json"),
        "subscription_clash_path": _normalize_path(payload.get("subscription_clash_path"), "/clash"),
    }


def list_nodes(settings: Settings) -> list[Dict[str, Any]]:
    rows = query(settings, "SELECT * FROM catalog_nodes ORDER BY id ASC")
    result = []
    for item in rows:
        result.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "display_name": build_node_display_name(item.get("name") or "", item.get("address") or ""),
                "scheme": item.get("scheme") or "https",
                "address": item.get("address") or "",
                "port": int(item.get("port") or 443),
                "base_path": normalize_base_path(item.get("base_path")),
                "subscription_scheme": item.get("subscription_scheme") or item.get("scheme") or "https",
                "subscription_address": item.get("subscription_address") or item.get("address") or "",
                "subscription_port": int(item.get("subscription_port") or 10882),
                "subscription_sub_path": _normalize_path(item.get("subscription_sub_path"), "/sub"),
                "subscription_json_path": _normalize_path(item.get("subscription_json_path"), "/json"),
                "subscription_clash_path": _normalize_path(item.get("subscription_clash_path"), "/clash"),
                "allow_insecure": bool(item.get("allow_insecure")),
                "last_status": item.get("last_status") or "unknown",
                "last_message": item.get("last_message") or "",
                "last_checked_at": item.get("last_checked_at"),
                "last_latency_ms": item.get("last_latency_ms"),
                "consecutive_failures": int(item.get("consecutive_failures") or 0),
                "abnormal_notified_at": item.get("abnormal_notified_at") or "",
                "inbounds": [],
            }
        )
        try:
            result[-1]["inbounds"] = list_node_inbounds(item)
        except ThreeXUIError:
            result[-1]["inbounds"] = []
    return result


def _save_probe_result(settings: Settings, node_id: int, ok: bool, message: str, probe: Dict[str, Any] | None = None) -> int:
    probe = probe or {}
    if ok:
        execute(
            settings,
            """
            UPDATE catalog_nodes
            SET last_status = ?, last_message = ?, last_checked_at = ?, last_latency_ms = ?,
                consecutive_failures = 0, abnormal_notified_at = NULL
            WHERE id = ?
            """,
            (
                "online",
                message,
                _now_text(),
                probe.get("latency_ms"),
                node_id,
            ),
        )
        return 0

    rows = query(settings, "SELECT consecutive_failures FROM catalog_nodes WHERE id = ?", (node_id,))
    failure_count = int((rows[0].get("consecutive_failures") if rows else 0) or 0) + 1
    execute(
        settings,
        """
        UPDATE catalog_nodes
        SET last_status = ?, last_message = ?, last_checked_at = ?, last_latency_ms = ?,
            consecutive_failures = ?
        WHERE id = ?
        """,
        (
            "offline",
            message,
            _now_text(),
            None,
            failure_count,
            node_id,
        ),
    )
    return failure_count


def _mark_node_abnormal_notified(settings: Settings, node_id: int) -> None:
    execute(settings, "UPDATE catalog_nodes SET abnormal_notified_at = ? WHERE id = ?", (_now_text(), node_id))


def verify_node_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = (payload.get("name") or "").strip()
    address = (payload.get("address") or "").strip()
    api_token = (payload.get("api_token") or "").strip()
    scheme = (payload.get("scheme") or "https").strip().lower()
    base_path = normalize_base_path(payload.get("base_path"))
    allow_insecure = bool(payload.get("allow_insecure"))
    port_raw = payload.get("port")
    subscription = _subscription_defaults({**payload, "scheme": scheme, "address": address})

    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="节点名称不能为空")
    if not address:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="面板地址不能为空")
    if not api_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API Token 不能为空")
    if scheme not in ("http", "https"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="协议只支持 http 或 https")

    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="端口格式不正确")
    if port <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="端口必须大于 0")

    return {
        "name": name,
        "scheme": scheme,
        "address": address,
        "port": port,
        "base_path": base_path,
        "api_token": api_token,
        "allow_insecure": allow_insecure,
        **subscription,
    }


def test_node_connection(payload: Dict[str, Any]) -> Dict[str, Any]:
    clean_payload = verify_node_payload(payload)
    probe = test_panel_connection(clean_payload)
    return {
        "success": True,
        "message": "节点连接验证成功",
        "data": probe,
    }


def create_node(settings: Settings, payload: Dict[str, Any]) -> Dict[str, Any]:
    clean_payload = verify_node_payload(payload)
    duplicate = query(settings, "SELECT id FROM catalog_nodes WHERE name = ?", (clean_payload["name"],))
    if duplicate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已存在同名节点")

    probe = test_panel_connection(clean_payload)
    node_id = execute(
        settings,
        """
        INSERT INTO catalog_nodes
        (name, scheme, address, port, base_path, api_token, allow_insecure, subscription_scheme, subscription_address, subscription_port, subscription_sub_path, subscription_json_path, subscription_clash_path, last_status, last_message, last_checked_at, last_latency_ms, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clean_payload["name"],
            clean_payload["scheme"],
            clean_payload["address"],
            clean_payload["port"],
            clean_payload["base_path"],
            clean_payload["api_token"],
            1 if clean_payload["allow_insecure"] else 0,
            clean_payload["subscription_scheme"],
            clean_payload["subscription_address"],
            clean_payload["subscription_port"],
            clean_payload["subscription_sub_path"],
            clean_payload["subscription_json_path"],
            clean_payload["subscription_clash_path"],
            "online",
            "连接正常",
            _now_text(),
            probe.get("latency_ms"),
            _now_text(),
        ),
    )
    return {"success": True, "message": "节点添加成功", "id": node_id, "probe": probe}


def update_node(settings: Settings, node_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    clean_payload = verify_node_payload(payload)
    current = query(settings, "SELECT id FROM catalog_nodes WHERE id = ?", (node_id,))
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在")

    duplicate = query(settings, "SELECT id FROM catalog_nodes WHERE name = ? AND id <> ?", (clean_payload["name"], node_id))
    if duplicate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="已存在同名节点")

    probe = test_panel_connection(clean_payload)
    execute(
        settings,
        """
        UPDATE catalog_nodes
        SET name = ?, scheme = ?, address = ?, port = ?, base_path = ?, api_token = ?, allow_insecure = ?,
            subscription_scheme = ?, subscription_address = ?, subscription_port = ?, subscription_sub_path = ?, subscription_json_path = ?, subscription_clash_path = ?,
            last_status = ?, last_message = ?, last_checked_at = ?, last_latency_ms = ?
        WHERE id = ?
        """,
        (
            clean_payload["name"],
            clean_payload["scheme"],
            clean_payload["address"],
            clean_payload["port"],
            clean_payload["base_path"],
            clean_payload["api_token"],
            1 if clean_payload["allow_insecure"] else 0,
            clean_payload["subscription_scheme"],
            clean_payload["subscription_address"],
            clean_payload["subscription_port"],
            clean_payload["subscription_sub_path"],
            clean_payload["subscription_json_path"],
            clean_payload["subscription_clash_path"],
            "online",
            "连接正常",
            _now_text(),
            probe.get("latency_ms"),
            node_id,
        ),
    )
    execute(
        settings,
        "UPDATE remote_customer_profiles SET node_name = ? WHERE node_id = ?",
        (clean_payload["name"], node_id),
    )
    return {"success": True, "message": "节点更新成功", "probe": probe}


def delete_node(settings: Settings, node_id: int) -> Dict[str, Any]:
    item_rows = query(settings, "SELECT name FROM catalog_nodes WHERE id = ?", (node_id,))
    if not item_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在")
    node_name = item_rows[0].get("name")
    profile_usage = query(settings, "SELECT COUNT(1) AS cnt FROM remote_customer_profiles WHERE node_id = ?", (node_id,))
    if (profile_usage[0].get("cnt") or 0) > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该节点下仍有关联客户，无法删除")
    legacy_usage = query(settings, "SELECT COUNT(1) AS cnt FROM customers WHERE node = ?", (node_name,))
    if (legacy_usage[0].get("cnt") or 0) > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该节点仍被旧客户数据使用，暂无法删除")
    execute(settings, "DELETE FROM catalog_nodes WHERE id = ?", (node_id,))
    return {"success": True, "message": "节点删除成功"}


def probe_existing_node(settings: Settings, node_id: int) -> Dict[str, Any]:
    rows = query(settings, "SELECT * FROM catalog_nodes WHERE id = ?", (node_id,))
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="节点不存在")
    node = rows[0]
    try:
        probe = test_panel_connection(node)
        _save_probe_result(settings, node_id, True, "连接正常", probe)
        return {"success": True, "message": "节点探测成功", "data": probe}
    except Exception as exc:
        _save_probe_result(settings, node_id, False, str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def probe_all_nodes(settings: Settings, *, notify_on_transition: bool = True, actor: str = "system") -> Dict[str, Any]:
    nodes = query(settings, "SELECT * FROM catalog_nodes ORDER BY id ASC")
    results: list[Dict[str, Any]] = []
    online_count = 0
    offline_count = 0

    for node in nodes:
        node_id = int(node.get("id") or 0)
        node_name = node.get("name") or str(node_id)
        previous_status = (node.get("last_status") or "unknown").strip().lower()
        try:
            probe = test_panel_connection(node)
            _save_probe_result(settings, node_id, True, "连接正常", probe)
            online_count += 1
            results.append(
                {
                    "id": node_id,
                    "name": node_name,
                    "status": "online",
                    "message": "连接正常",
                    "latency_ms": probe.get("latency_ms"),
                }
            )
        except Exception as exc:
            message = str(exc)
            failure_count = _save_probe_result(settings, node_id, False, message)
            offline_count += 1
            became_offline = previous_status != "offline"
            already_notified = bool(node.get("abnormal_notified_at"))
            should_notify = (
                notify_on_transition
                and failure_count >= NODE_ABNORMAL_NOTIFY_FAILURE_THRESHOLD
                and not already_notified
            )
            notified = False
            if should_notify:
                from backend.app.services.notifications import notify_node_abnormal

                notified = bool(notify_node_abnormal(settings, node_id, message))
                if notified:
                    _mark_node_abnormal_notified(settings, node_id)
            if became_offline or should_notify:
                write_activity_log(
                    settings,
                    category="node",
                    action="auto_probe",
                    actor=actor,
                    target_type="node",
                    target_id=str(node_id),
                    target_name=node_name,
                    status="failed",
                    summary=f"自动探测节点失败：{node_name}",
                    detail={
                        "error": message,
                        "previous_status": previous_status,
                        "failure_count": failure_count,
                        "notify_threshold": NODE_ABNORMAL_NOTIFY_FAILURE_THRESHOLD,
                        "notified": notified,
                    },
                )
            results.append(
                {
                    "id": node_id,
                    "name": node_name,
                    "status": "offline",
                    "message": message,
                    "failure_count": failure_count,
                    "notify_threshold": NODE_ABNORMAL_NOTIFY_FAILURE_THRESHOLD,
                    "notified": notified,
                }
            )

    record_task_state(
        settings,
        category="node",
        action="auto_probe",
        actor=actor,
        status="failed" if offline_count and online_count == 0 and nodes else "partial" if offline_count else "success",
        summary=f"节点自动探测完成：在线 {online_count} / 离线 {offline_count} / 总计 {len(nodes)}",
        detail={"total": len(nodes), "online": online_count, "offline": offline_count, "items": results},
    )
    return {
        "success": True,
        "message": "节点自动探测完成",
        "total": len(nodes),
        "online": online_count,
        "offline": offline_count,
        "items": results,
    }


def fetch_node_subscription_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    clean_payload = verify_node_payload(payload)
    raw = get_panel_settings(clean_payload)
    subscription = raw.get("subscription") if isinstance(raw.get("subscription"), dict) else raw
    scheme = str(_first_setting_value(subscription, "subScheme", "subscriptionScheme", "subProtocol") or clean_payload["scheme"]).lower()
    address = str(_first_setting_value(subscription, "subDomain", "subscriptionDomain", "subHost", "subscriptionHost") or clean_payload["address"]).strip()
    port_raw = _first_setting_value(subscription, "subPort", "subscriptionPort", "subListenPort")
    try:
        port = int(port_raw or 10882)
    except (TypeError, ValueError):
        port = 10882
    return {
        "success": True,
        "message": "订阅配置已读取",
        "data": {
            "subscription_scheme": scheme if scheme in ("http", "https") else clean_payload["scheme"],
            "subscription_address": address,
            "subscription_port": port if port > 0 else 10882,
            "subscription_sub_path": _normalize_path(str(_first_setting_value(subscription, "subPath", "subscriptionPath") or "/sub"), "/sub"),
            "subscription_json_path": _normalize_path(str(_first_setting_value(subscription, "subJsonPath", "jsonSubPath", "subscriptionJsonPath") or "/json"), "/json"),
            "subscription_clash_path": _normalize_path(str(_first_setting_value(subscription, "subClashPath", "clashSubPath", "subscriptionClashPath") or "/clash"), "/clash"),
        },
    }


def add_catalog_item(settings: Settings, table_name: str, item_name: str) -> Tuple[bool, str]:
    clean_name = (item_name or "").strip()
    if not clean_name:
        return False, "名称不能为空"

    existing = query(settings, f"SELECT id FROM {table_name} WHERE name = ?", (clean_name,))
    if existing:
        return False, "已存在同名项"

    execute(
        settings,
        f"INSERT INTO {table_name} (name, created_at) VALUES (?, ?)",
        (clean_name, _now_text()),
    )
    return True, "添加成功"


def delete_catalog_item(settings: Settings, table_name: str, item_id: int) -> Tuple[bool, str]:
    item_rows = query(settings, f"SELECT name FROM {table_name} WHERE id = ?", (item_id,))
    if not item_rows:
        return False, "目标项不存在"
    item_name = item_rows[0].get("name")

    if table_name == "catalog_managers":
        usage_rows = query(settings, "SELECT COUNT(1) AS cnt FROM customers WHERE manager = ?", (item_name,))
        if (usage_rows[0].get("cnt") or 0) > 0:
            return False, "该客户经理仍有关联客户，无法删除"
        remote_usage_rows = query(settings, "SELECT COUNT(1) AS cnt FROM remote_customer_profiles WHERE manager = ?", (item_name,))
        if (remote_usage_rows[0].get("cnt") or 0) > 0:
            return False, "该客户经理仍有关联远程客户，无法删除"

    execute(settings, f"DELETE FROM {table_name} WHERE id = ?", (item_id,))
    return True, "删除成功"


def get_settings_options(settings: Settings) -> Dict[str, Any]:
    manager_rows = query(
        settings,
        "SELECT id, username, nickname, enabled, role FROM users WHERE COALESCE(enabled, 1) = 1 ORDER BY id ASC",
    )
    managers = []
    for item in manager_rows:
        display_name = (item.get("nickname") or item.get("username") or "").strip()
        if not display_name:
            continue
        managers.append(
            {
                "id": item.get("id"),
                "name": display_name,
                "username": item.get("username") or "",
                "nickname": item.get("nickname") or "",
                "role": item.get("role") or "user",
            }
        )
    return {
        "success": True,
        "nodes": list_nodes(settings),
        "managers": managers,
        "notification": {
            "push_mode": get_setting(settings, "push_mode", settings.default_push_mode),
            "max_detail_rows": get_int_setting(settings, "max_detail_rows", settings.default_max_detail_rows),
            "fixed_push_time": get_setting(settings, "fixed_push_time", settings.default_fixed_push_time),
            "fixed_push_time_enabled": get_bool_setting(settings, "fixed_push_time_enabled", False),
            "push_time_window_minutes": get_int_setting(settings, "push_time_window_minutes", settings.default_push_time_window_minutes),
        },
    }
