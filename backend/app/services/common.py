import json
import re
from datetime import datetime
from typing import Dict, List, Tuple

from backend.app.core.config import Settings
from backend.app.db.database import get_setting, query


def parse_json_list(raw_value: str, fallback: List[str]) -> List[str]:
    try:
        data = json.loads(raw_value) if raw_value else []
        if isinstance(data, list):
            values = [str(x).strip() for x in data if str(x).strip()]
            return values or fallback
    except Exception:
        pass
    return fallback


def normalize_numeric_amount(price_text):
    if not price_text:
        return None
    cleaned = "".join(re.findall(r"[0-9.]", str(price_text)))
    if not cleaned:
        return None
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def calculate_remaining_days(expiry_date_str: str) -> int:
    try:
        if not (expiry_date_str or "").strip():
            return 999999
        expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        return (expiry_date - today).days
    except Exception:
        return 0


def map_customer_status(rem_days: int, *, is_enabled: bool = True, is_unlimited: bool = False) -> Tuple[str, str]:
    if not is_enabled:
        return "已停用", "disabled"
    if is_unlimited:
        return "无限期", "unlimited"
    if rem_days < 0:
        return f"已过期 {abs(rem_days)} 天", "expired"
    if rem_days == 0:
        return "今天到期", "today"
    if rem_days <= 7:
        return f"剩余 {rem_days} 天", "warning"
    return f"剩余 {rem_days} 天", "healthy"


def render_notification_message(template: str, customer: Dict, rem_days: int, current_time_str: str, settings: Settings) -> str:
    if customer.get("is_unlimited_expiry"):
        rem_days_text = "无限期"
        status_text = "无限期"
    elif not customer.get("enable", True):
        rem_days_text = "已停用"
        status_text = "已停用"
    elif rem_days < 0:
        rem_days_text = f"已过期 {abs(rem_days)} 天"
        status_text = "已过期"
    elif rem_days == 0:
        rem_days_text = "今天到期"
        status_text = "今日到期"
    else:
        rem_days_text = f"{rem_days} 天"
        status_text = "即将到期"

    payload_map = {
        "name": customer["name"],
        "manager": customer.get("manager", "未分配"),
        "node": customer["node"],
        "price": customer.get("renew_price", "未设置"),
        "expiry": customer.get("expiry_display") or customer.get("expiry_date") or "-",
        "rem": rem_days_text,
        "status": status_text,
        "time": current_time_str,
    }
    try:
        return template.format(**payload_map)
    except Exception:
        return settings.default_notification_template.format(**payload_map)


def get_int_setting(settings: Settings, key: str, default_val: int) -> int:
    raw = (get_setting(settings, key, str(default_val)) or "").strip()
    try:
        val = int(raw)
        return val if val > 0 else default_val
    except Exception:
        return default_val


def get_bool_setting(settings: Settings, key: str, default_val: bool = False) -> bool:
    default_raw = "1" if default_val else "0"
    raw = (get_setting(settings, key, default_raw) or default_raw).strip().lower()
    return raw in ("1", "true", "yes", "on")


def is_now_within_push_window(now_dt, fixed_time_text: str, window_minutes: int) -> bool:
    try:
        target_time = datetime.strptime(fixed_time_text, "%H:%M").time()
    except ValueError:
        target_time = datetime.strptime("09:00", "%H:%M").time()

    target_dt = datetime.combine(now_dt.date(), target_time)
    diff_minutes = (now_dt - target_dt).total_seconds() / 60
    return 0 <= diff_minutes <= max(1, window_minutes)


def get_node_options(settings: Settings) -> List[str]:
    rows = query(settings, "SELECT name FROM catalog_nodes ORDER BY id ASC")
    values = [r["name"] for r in rows]
    return values


def get_manager_options(settings: Settings) -> List[str]:
    rows = query(
        settings,
        "SELECT username FROM users WHERE COALESCE(enabled, 1) = 1 ORDER BY id ASC",
    )
    values = [r["username"] for r in rows]
    return values


def build_customer_row(customer: Dict) -> Dict:
    is_unlimited = bool(customer.get("is_unlimited_expiry"))
    expiry_date = customer.get("expiry_date") or ""
    rem = calculate_remaining_days(expiry_date)
    if is_unlimited:
        rem = 999999
    is_enabled = bool(customer.get("enable", True))
    status_text, status_level = map_customer_status(rem, is_enabled=is_enabled, is_unlimited=is_unlimited)
    return {
        "id": customer["id"],
        "name": customer["name"],
        "manager": customer.get("manager") or "未分配",
        "node": customer["node"],
        "renew_price": customer.get("renew_price") or "未设置",
        "expiry_date": expiry_date,
        "expiry_display": customer.get("expiry_display") or ("无限期" if is_unlimited else expiry_date or "-"),
        "duration": customer.get("duration", "-"),
        "remaining_days": rem,
        "status_text": status_text,
        "status_level": status_level,
        "is_unlimited_expiry": is_unlimited,
        "enable": is_enabled,
    }
