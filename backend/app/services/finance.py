from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from time import monotonic
from typing import Any, Dict

from fastapi import HTTPException, status

from backend.app.core.config import Settings
from backend.app.db.database import execute, query
from backend.app.services.dashboard import clear_dashboard_cache
from backend.app.services.logs import write_activity_log


EDITABLE_FIELDS = {
    "customer_name",
    "owner_username",
    "renew_price",
    "amount",
    "renew_days",
    "new_expiry",
    "created_at",
}
_FINANCE_CACHE: dict[tuple, tuple[float, Dict[str, Any]]] = {}
_FINANCE_CACHE_LOCK = Lock()
_FINANCE_CACHE_TTL_SECONDS = 15


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_datetime(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} 不能为空")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text, fmt)
            if fmt == "%Y-%m-%d":
                parsed = parsed.replace(hour=0, minute=0, second=0)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} 格式不正确")


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    for key in EDITABLE_FIELDS:
        if key not in payload:
            continue
        value = payload.get(key)
        if key in {"customer_name", "renew_price", "new_expiry"}:
            clean = str(value or "").strip()
            if not clean:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} 不能为空")
            updates[key] = clean
        elif key == "owner_username":
            updates[key] = str(value or "").strip()
        elif key == "amount":
            try:
                updates[key] = round(float(value), 2)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="金额格式不正确") from exc
        elif key == "renew_days":
            try:
                days = int(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="续费天数格式不正确") from exc
            updates[key] = days
        elif key == "created_at":
            updates[key] = _normalize_datetime(value, "流水时间")
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可修改的字段")
    return updates


def _get_financial_log(settings: Settings, log_id: int) -> Dict[str, Any]:
    rows = query(settings, "SELECT * FROM financial_logs WHERE id = ? LIMIT 1", (log_id,))
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="财务流水不存在")
    return rows[0]


def _settings_cache_key(settings: Settings) -> tuple:
    if settings.db_type == "mysql":
        mysql = settings.mysql_config or {}
        return ("mysql", mysql.get("host") or "", mysql.get("port") or "", mysql.get("database") or "")
    return ("sqlite", settings.sqlite_file)


def clear_finance_cache() -> None:
    with _FINANCE_CACHE_LOCK:
        _FINANCE_CACHE.clear()


def list_financial_logs(
    settings: Settings,
    *,
    page: int = 1,
    per_page: int = 20,
    keyword: str = "",
    owner_username: str = "",
    node_id: int | None = None,
    date_from: str = "",
    date_to: str = "",
) -> Dict[str, Any]:
    page = max(int(page or 1), 1)
    per_page = min(max(int(per_page or 20), 1), 100)
    clauses: list[str] = []
    params: list[Any] = []
    clean_keyword = (keyword or "").strip()
    if clean_keyword:
        clauses.append("(f.customer_name LIKE ? OR f.renew_price LIKE ? OR f.remote_email LIKE ? OR f.owner_username LIKE ?)")
        params.extend([f"%{clean_keyword}%"] * 4)
    if owner_username.strip():
        clauses.append("f.owner_username = ?")
        params.append(owner_username.strip())
    if node_id:
        clauses.append("f.node_id = ?")
        params.append(int(node_id))
    if date_from.strip():
        clauses.append("f.created_at >= ?")
        params.append(_normalize_datetime(date_from.strip(), "开始时间"))
    if date_to.strip():
        clauses.append("f.created_at <= ?")
        params.append(_normalize_datetime(date_to.strip(), "结束时间"))
    cache_key = (
        _settings_cache_key(settings),
        page,
        per_page,
        clean_keyword,
        owner_username.strip(),
        int(node_id or 0),
        date_from.strip(),
        date_to.strip(),
    )
    now = monotonic()
    with _FINANCE_CACHE_LOCK:
        cached = _FINANCE_CACHE.get(cache_key)
        if cached and now - cached[0] <= _FINANCE_CACHE_TTL_SECONDS:
            return deepcopy(cached[1])

    where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    total_rows = query(settings, f"SELECT COUNT(1) AS cnt FROM financial_logs f {where_sql}", tuple(params))
    total = int(total_rows[0].get("cnt") or 0) if total_rows else 0
    total_amount_rows = query(settings, f"SELECT COALESCE(SUM(f.amount), 0) AS total_amount FROM financial_logs f {where_sql}", tuple(params))
    total_amount = round(float(total_amount_rows[0].get("total_amount") or 0), 2) if total_amount_rows else 0.0
    rows = query(
        settings,
        f"""
        SELECT f.id, f.customer_id, f.owner_username, f.node_id, n.name AS node_name, f.remote_email, f.customer_name, f.renew_price, f.amount, f.renew_days, f.new_expiry, f.created_at
        FROM financial_logs f
        LEFT JOIN catalog_nodes n ON n.id = f.node_id
        {where_sql}
        ORDER BY f.id DESC
        LIMIT ? OFFSET ?
        """,
        tuple(params + [per_page, (page - 1) * per_page]),
    )
    result = {"items": rows, "total": total, "page": page, "per_page": per_page, "total_amount": total_amount}
    with _FINANCE_CACHE_LOCK:
        _FINANCE_CACHE[cache_key] = (now, deepcopy(result))
    return result


def update_financial_log(settings: Settings, log_id: int, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    before = _get_financial_log(settings, log_id)
    updates = _normalize_payload(payload)
    set_sql = ", ".join(f"{key} = ?" for key in updates)
    execute(settings, f"UPDATE financial_logs SET {set_sql} WHERE id = ?", tuple(updates.values()) + (log_id,))
    after = _get_financial_log(settings, log_id)
    clear_finance_cache()
    clear_dashboard_cache()
    write_activity_log(
        settings,
        category="finance",
        action="update_financial_log",
        actor=actor,
        target_type="financial_log",
        target_id=str(log_id),
        target_name=after.get("customer_name") or "",
        status="success",
        summary=f"修改财务流水：{after.get('customer_name') or log_id}",
        detail={"before": before, "after": after},
    )
    return {"success": True, "message": "财务流水已更新", "data": after}


def delete_financial_log(settings: Settings, log_id: int, *, actor: str = "") -> Dict[str, Any]:
    before = _get_financial_log(settings, log_id)
    execute(settings, "DELETE FROM financial_logs WHERE id = ?", (log_id,))
    clear_finance_cache()
    clear_dashboard_cache()
    write_activity_log(
        settings,
        category="finance",
        action="delete_financial_log",
        actor=actor,
        target_type="financial_log",
        target_id=str(log_id),
        target_name=before.get("customer_name") or "",
        status="success",
        summary=f"删除财务流水：{before.get('customer_name') or log_id}",
        detail=before,
    )
    return {"success": True, "message": "财务流水已删除"}
