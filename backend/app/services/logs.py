import json
from datetime import datetime
from typing import Any, Dict, List

import requests

from backend.app.core.config import Settings
from backend.app.db.database import execute, query


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_activity_log(
    settings: Settings,
    *,
    category: str,
    action: str,
    actor: str = "",
    target_type: str = "",
    target_id: str = "",
    target_name: str = "",
    status: str = "success",
    summary: str,
    detail: Any = None,
    ip_address: str = "",
) -> None:
    detail_text = detail if isinstance(detail, str) else json.dumps(detail or {}, ensure_ascii=False)
    execute(
        settings,
        """
        INSERT INTO activity_logs (category, action, actor, target_type, target_id, target_name, status, summary, detail, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (category, action, actor, target_type, target_id, target_name, status, summary, detail_text, ip_address, _now_text()),
    )


def create_notification_log(
    settings: Settings,
    *,
    event_type: str,
    send_mode: str,
    webhook_url: str,
    payload: Dict[str, Any],
    customer_id: str = "",
    node_id: int | None = None,
    remote_email: str = "",
    customer_name: str = "",
    manager: str = "",
    status: str = "pending",
    response_status: int | None = None,
    response_text: str = "",
    error_message: str = "",
) -> int | None:
    return execute(
        settings,
        """
        INSERT INTO notification_logs
        (event_type, send_mode, customer_id, node_id, remote_email, customer_name, manager, webhook_url, payload, status, response_status, response_text, error_message, created_at, sent_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_type,
            send_mode,
            customer_id,
            node_id,
            remote_email,
            customer_name,
            manager,
            webhook_url,
            json.dumps(payload, ensure_ascii=False),
            status,
            response_status,
            response_text,
            error_message,
            _now_text(),
            _now_text() if status in ("success", "failed") else None,
        ),
    )


def update_notification_result(
    settings: Settings,
    log_id: int | None,
    *,
    status: str,
    response_status: int | None = None,
    response_text: str = "",
    error_message: str = "",
    retry_count_increment: bool = False,
) -> None:
    if not log_id:
        return
    retry_sql = ", retry_count = retry_count + 1, last_retry_at = ?" if retry_count_increment else ""
    params: list[Any] = [status, response_status, response_text, error_message, _now_text()]
    if retry_count_increment:
        params.append(_now_text())
    params.append(log_id)
    execute(
        settings,
        f"""
        UPDATE notification_logs
        SET status = ?, response_status = ?, response_text = ?, error_message = ?, sent_at = ?{retry_sql}
        WHERE id = ?
        """,
        tuple(params),
    )


def _customer_audit_as_activity(row: Dict[str, Any]) -> Dict[str, Any]:
    node_id = row.get("node_id")
    remote_email = row.get("remote_email") or ""
    return {
        "id": f"customer-{row.get('id')}",
        "category": "customer",
        "action": row.get("action") or "",
        "actor": row.get("actor") or "",
        "target_type": "customer",
        "target_id": f"{node_id}:{remote_email}" if node_id and remote_email else str(row.get("id") or ""),
        "target_name": row.get("customer_name") or "",
        "status": "success",
        "summary": row.get("change_summary") or "",
        "detail": json.dumps(
            {
                "source": "customer_audit_logs",
                "customer_name": row.get("customer_name") or "",
                "node_id": node_id,
                "remote_email": remote_email,
                "change_summary": row.get("change_summary") or "",
            },
            ensure_ascii=False,
        ),
        "ip_address": "",
        "created_at": row.get("created_at") or "",
    }


def _list_activity_table_rows(settings: Settings, category: str = "", keyword: str = "") -> List[Dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if category:
        clauses.append("category = ?")
        params.append(category)
    if keyword:
        clauses.append("(summary LIKE ? OR actor LIKE ? OR target_name LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return query(
        settings,
        f"""
        SELECT id, category, action, actor, target_type, target_id, target_name, status, summary, detail, ip_address, created_at
        FROM activity_logs
        {where_sql}
        ORDER BY id DESC
        """,
        tuple(params),
    )


def _list_customer_audit_activity_rows(settings: Settings, keyword: str = "") -> List[Dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if keyword:
        clauses.append("(change_summary LIKE ? OR actor LIKE ? OR customer_name LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = query(
        settings,
        f"""
        SELECT id, node_id, remote_email, customer_name, action, actor, change_summary, created_at
        FROM customer_audit_logs
        {where_sql}
        ORDER BY id DESC
        """,
        tuple(params),
    )
    return [_customer_audit_as_activity(row) for row in rows]


def list_activity_logs(settings: Settings, page: int = 1, per_page: int = 20, category: str = "", keyword: str = "") -> Dict[str, Any]:
    clean_category = (category or "").strip()
    rows: List[Dict[str, Any]] = []
    rows.extend(_list_activity_table_rows(settings, clean_category, keyword))
    if clean_category in ("", "customer"):
        rows.extend(_list_customer_audit_activity_rows(settings, keyword))

    rows.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")), reverse=True)
    total = len(rows)
    start = max(page - 1, 0) * per_page
    paged_rows = rows[start : start + per_page]
    return {"items": paged_rows, "total": total, "page": page, "per_page": per_page}


def list_activity_categories(settings: Settings) -> List[str]:
    rows = query(settings, "SELECT DISTINCT category FROM activity_logs WHERE category IS NOT NULL AND category <> '' ORDER BY category ASC")
    categories = {str(row.get("category") or "").strip() for row in rows if str(row.get("category") or "").strip()}
    customer_rows = query(settings, "SELECT id FROM customer_audit_logs LIMIT 1")
    if customer_rows:
        categories.add("customer")
    return sorted(categories)


def list_notification_logs(
    settings: Settings,
    page: int = 1,
    per_page: int = 20,
    status: str = "",
    event_type: str = "",
    customer_id: str = "",
) -> Dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if customer_id:
        clauses.append("customer_id = ?")
        params.append(customer_id)
    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total_rows = query(settings, f"SELECT COUNT(1) AS cnt FROM notification_logs {where_sql}", tuple(params))
    total = int(total_rows[0].get("cnt") or 0) if total_rows else 0
    rows = query(
        settings,
        f"""
        SELECT id, event_type, send_mode, customer_id, node_id, remote_email, customer_name, manager, webhook_url,
               status, response_status, response_text, error_message, retry_count, last_retry_at, created_at, sent_at
        FROM notification_logs
        {where_sql}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params + [per_page, (page - 1) * per_page]),
    )
    return {"items": rows, "total": total, "page": page, "per_page": per_page}


def retry_notification(settings: Settings, log_id: int) -> Dict[str, Any]:
    rows = query(settings, "SELECT * FROM notification_logs WHERE id = ?", (log_id,))
    if not rows:
        return {"success": False, "message": "找不到通知日志"}
    row = rows[0]
    try:
        payload = json.loads(row.get("payload") or "{}")
    except Exception:
        payload = {}
    webhook = row.get("webhook_url") or ""
    if not webhook:
        update_notification_result(settings, log_id, status="failed", error_message="Webhook 为空", retry_count_increment=True)
        return {"success": False, "message": "Webhook 为空"}
    try:
        response = requests.post(
            webhook,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=8,
        )
        ok = response.status_code in (200, 201)
        update_notification_result(
            settings,
            log_id,
            status="success" if ok else "failed",
            response_status=response.status_code,
            response_text=response.text[:1000],
            error_message="" if ok else f"HTTP {response.status_code}",
            retry_count_increment=True,
        )
        return {"success": ok, "message": "重试发送成功" if ok else f"重试发送失败：HTTP {response.status_code}"}
    except Exception as exc:
        update_notification_result(settings, log_id, status="failed", error_message=str(exc), retry_count_increment=True)
        return {"success": False, "message": f"重试发送失败：{exc}"}
