import json
import time
from datetime import datetime
from typing import Any, Dict, List

from backend.app.core.config import Settings
from backend.app.db.database import query
from backend.app.services.task_state import read_task_state


SERVICE_STARTED_AT = datetime.now()


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _latest_activity(settings: Settings, category: str = "", action: str = "") -> Dict[str, Any] | None:
    clauses: list[str] = []
    params: list[Any] = []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if action:
        clauses.append("action = ?")
        params.append(action)
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = query(
        settings,
        f"""
        SELECT id, category, action, actor, status, summary, detail, created_at
        FROM activity_logs
        {where_sql}
        ORDER BY id DESC
        LIMIT 1
        """,
        tuple(params),
    )
    return rows[0] if rows else None


def _latest_auto_task(settings: Settings) -> Dict[str, Any] | None:
    states = [
        read_task_state(settings, "node", "auto_probe"),
        read_task_state(settings, "notification", "webhook_check"),
    ]
    states = [item for item in states if item]
    if states:
        return sorted(states, key=lambda item: str(item.get("created_at") or ""), reverse=True)[0]
    rows = query(
        settings,
        """
        SELECT id, category, action, actor, status, summary, detail, created_at
        FROM activity_logs
        WHERE (category = ? AND action = ?) OR (category = ? AND action = ?)
        ORDER BY id DESC
        LIMIT 1
        """,
        ("node", "auto_probe", "notification", "webhook_check"),
    )
    return rows[0] if rows else None


def _latest_notification_log(settings: Settings) -> Dict[str, Any] | None:
    rows = query(
        settings,
        """
        SELECT id, event_type, send_mode, status, error_message, created_at, sent_at
        FROM notification_logs
        ORDER BY id DESC
        LIMIT 1
        """,
    )
    return rows[0] if rows else None


def _parse_detail(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        return json.loads(value)
    except Exception:
        return value


def _normalize_activity(row: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row.get("id"),
        "category": row.get("category") or "",
        "action": row.get("action") or "",
        "actor": row.get("actor") or "",
        "status": row.get("status") or "unknown",
        "summary": row.get("summary") or "",
        "detail": _parse_detail(row.get("detail")),
        "created_at": row.get("created_at") or "",
    }


def _database_status(settings: Settings) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        query(settings, "SELECT 1 AS ok")
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {"status": "online", "ok": True, "latency_ms": latency_ms, "message": "数据库连接正常"}
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {"status": "offline", "ok": False, "latency_ms": latency_ms, "message": str(exc)}


def _node_status(settings: Settings) -> Dict[str, Any]:
    rows = query(
        settings,
        """
        SELECT id, name, address, port, last_status, last_message, last_checked_at, last_latency_ms
        FROM catalog_nodes
        ORDER BY id ASC
        """,
    )
    items: List[Dict[str, Any]] = []
    online = 0
    offline = 0
    unknown = 0
    latest_checked_at = ""

    for row in rows:
        status = str(row.get("last_status") or "unknown").strip().lower() or "unknown"
        if status == "online":
            online += 1
        elif status == "offline":
            offline += 1
        else:
            unknown += 1
        checked_at = str(row.get("last_checked_at") or "")
        if checked_at and checked_at > latest_checked_at:
            latest_checked_at = checked_at
        items.append(
            {
                "id": row.get("id"),
                "name": row.get("name") or "",
                "address": row.get("address") or "",
                "port": row.get("port"),
                "status": status,
                "message": row.get("last_message") or "",
                "last_checked_at": checked_at,
                "latency_ms": row.get("last_latency_ms"),
            }
        )

    total = len(items)
    if total == 0:
        status = "unknown"
        message = "尚未配置节点"
    elif offline > 0:
        status = "degraded"
        message = f"{offline} 个节点离线"
    elif unknown > 0:
        status = "unknown"
        message = f"{unknown} 个节点尚未探测"
    else:
        status = "online"
        message = "节点探测状态正常"

    return {
        "status": status,
        "message": message,
        "total": total,
        "online": online,
        "offline": offline,
        "unknown": unknown,
        "latest_checked_at": latest_checked_at,
        "items": items,
    }


def _notification_status(settings: Settings) -> Dict[str, Any]:
    activity = _normalize_activity(read_task_state(settings, "notification", "webhook_check")) or _normalize_activity(_latest_activity(settings, "notification", "webhook_check"))
    latest_log = _latest_notification_log(settings)
    latest_at = ""
    if activity:
        latest_at = str(activity.get("created_at") or "")
    if latest_log:
        latest_log_at = str(latest_log.get("sent_at") or latest_log.get("created_at") or "")
        if latest_log_at > latest_at:
            latest_at = latest_log_at

    return {
        "last_checked_at": latest_at,
        "last_check": activity,
        "latest_notification_log": latest_log,
        "message": activity.get("summary") if activity else "尚未记录通知检查任务",
        "status": activity.get("status") if activity else "unknown",
    }


def get_system_health(settings: Settings) -> Dict[str, Any]:
    database = _database_status(settings)
    nodes: Dict[str, Any]
    notification: Dict[str, Any]
    latest_auto_task: Dict[str, Any] | None

    try:
        nodes = _node_status(settings)
    except Exception as exc:
        nodes = {"status": "unknown", "message": str(exc), "total": 0, "online": 0, "offline": 0, "unknown": 0, "items": []}

    try:
        notification = _notification_status(settings)
    except Exception as exc:
        notification = {"status": "unknown", "message": str(exc), "last_checked_at": "", "last_check": None, "latest_notification_log": None}

    try:
        latest_auto_task = _normalize_activity(_latest_auto_task(settings))
    except Exception:
        latest_auto_task = None

    return {
        "backend": {
            "status": "online",
            "ok": True,
            "message": "后端运行中",
            "app_name": settings.app_name,
            "version": settings.app_version,
            "started_at": SERVICE_STARTED_AT.strftime("%Y-%m-%d %H:%M:%S"),
            "checked_at": _now_text(),
        },
        "database": database,
        "nodes": nodes,
        "notification": notification,
        "latest_auto_task": latest_auto_task,
    }
