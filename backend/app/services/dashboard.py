from copy import deepcopy
from datetime import datetime, timedelta
from threading import Lock
from time import monotonic
from typing import Callable, Dict, List

from backend.app.core.config import Settings
from backend.app.db.database import query
from backend.app.services.common import calculate_remaining_days

_DASHBOARD_CACHE: dict[tuple, tuple[float, object]] = {}
_DASHBOARD_CACHE_LOCK = Lock()


def _settings_cache_key(settings: Settings) -> tuple:
    if settings.db_type == "mysql":
        mysql = settings.mysql_config or {}
        return (
            "mysql",
            mysql.get("host") or "",
            mysql.get("port") or "",
            mysql.get("database") or "",
        )
    return ("sqlite", settings.sqlite_file)


def _cache_ttl(settings: Settings) -> int:
    try:
        return max(int(getattr(settings, "dashboard_cache_ttl_seconds", 20)), 0)
    except (TypeError, ValueError):
        return 20


def _cached(settings: Settings, key: tuple, producer: Callable[[], object]) -> object:
    ttl = _cache_ttl(settings)
    if ttl <= 0:
        return producer()
    now = monotonic()
    cache_key = (_settings_cache_key(settings),) + key
    with _DASHBOARD_CACHE_LOCK:
        cached = _DASHBOARD_CACHE.get(cache_key)
        if cached and now - cached[0] <= ttl:
            return deepcopy(cached[1])
    value = producer()
    with _DASHBOARD_CACHE_LOCK:
        _DASHBOARD_CACHE[cache_key] = (now, deepcopy(value))
    return value


def clear_dashboard_cache() -> None:
    with _DASHBOARD_CACHE_LOCK:
        _DASHBOARD_CACHE.clear()


def get_dashboard_summary(settings: Settings, customers: List[Dict]) -> Dict:
    total_count = len(customers)
    expired_count = 0
    warning_count = 0
    disabled_count = 0
    healthy_count = 0
    for c in customers:
        if not c.get("enable", True):
            disabled_count += 1
            continue
        if c.get("is_unlimited_expiry"):
            healthy_count += 1
            continue
        rem = calculate_remaining_days(c["expiry_date"])
        if rem < 0:
            expired_count += 1
        elif rem <= 7:
            warning_count += 1
        else:
            healthy_count += 1

    return {
        "total_count": total_count,
        "healthy_count": healthy_count,
        "disabled_count": disabled_count,
        "expired_count": expired_count,
        "warning_count": warning_count,
    }


def get_cached_dashboard_status(settings: Settings, owner_username: str, actor_role: str, customers_loader: Callable[[], List[Dict]]) -> Dict:
    scope_key = ((owner_username or "").strip(), (actor_role or "user").strip().lower())
    return _cached(settings, ("dashboard_status", scope_key), lambda: get_dashboard_summary(settings, customers_loader()))  # type: ignore[return-value]


def _period_bounds(period: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now()
    clean_period = (period or "month").strip().lower()
    if clean_period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if clean_period == "week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, next_month


def _sum_income_between(
    settings: Settings,
    start: datetime,
    end: datetime,
    owner_username: str | None = None,
    actor_role: str = "admin",
) -> float:
    start_text = start.strftime("%Y-%m-%d %H:%M:%S")
    end_text = end.strftime("%Y-%m-%d %H:%M:%S")
    if (actor_role or "").strip().lower() == "admin":
        rows = query(
            settings,
            "SELECT COALESCE(SUM(amount), 0) AS income FROM financial_logs WHERE created_at >= ? AND created_at < ?",
            (start_text, end_text),
        )
    else:
        rows = query(
            settings,
            "SELECT COALESCE(SUM(amount), 0) AS income FROM financial_logs WHERE created_at >= ? AND created_at < ? AND owner_username = ?",
            (start_text, end_text, owner_username or ""),
        )
    return round(float((rows[0].get("income") if rows else 0) or 0), 2)


def get_period_income(settings: Settings, period: str = "month", owner_username: str | None = None, actor_role: str = "admin") -> float:
    start, end = _period_bounds(period)
    return _sum_income_between(settings, start, end, owner_username, actor_role)


def get_cached_period_income(settings: Settings, period: str = "month", owner_username: str | None = None, actor_role: str = "admin") -> float:
    clean_period = (period or "month").strip().lower()
    scope_key = (clean_period, (owner_username or "").strip(), (actor_role or "user").strip().lower())
    return float(_cached(settings, ("period_income", scope_key), lambda: get_period_income(settings, clean_period, owner_username, actor_role)))


def get_month_income(settings: Settings, owner_username: str | None = None, actor_role: str = "admin") -> float:
    return get_period_income(settings, "month", owner_username, actor_role)


def get_monthly_income_series(settings: Settings, owner_username: str | None = None, actor_role: str = "admin") -> List[Dict]:
    now = datetime.now().replace(day=1)
    months = []
    for i in range(5, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        month_key = f"{year}-{month:02d}"
        if (actor_role or "").strip().lower() == "admin":
            rows = query(
                settings,
                "SELECT COALESCE(SUM(amount), 0) AS total FROM financial_logs WHERE created_at LIKE ?",
                (f"{month_key}%",),
            )
        else:
            rows = query(
                settings,
                "SELECT COALESCE(SUM(amount), 0) AS total FROM financial_logs WHERE created_at LIKE ? AND owner_username = ?",
                (f"{month_key}%", owner_username or ""),
            )
        total = float((rows[0].get("total") if rows else 0) or 0)
        months.append({"month": month_key, "income": round(total, 2)})
    return months


def get_income_series(settings: Settings, period: str = "month", owner_username: str | None = None, actor_role: str = "admin") -> List[Dict]:
    clean_period = (period or "month").strip().lower()
    now = datetime.now()
    if clean_period == "today":
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return [
            {
                "month": (today - timedelta(days=6 - index)).strftime("%m-%d"),
                "income": _sum_income_between(
                    settings,
                    today - timedelta(days=6 - index),
                    today - timedelta(days=5 - index),
                    owner_username,
                    actor_role,
                ),
            }
            for index in range(7)
        ]
    if clean_period == "week":
        this_week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        rows: List[Dict] = []
        for index in range(8):
            start = this_week_start - timedelta(weeks=7 - index)
            end = start + timedelta(days=7)
            rows.append({"month": f"{start.strftime('%m-%d')} 周", "income": _sum_income_between(settings, start, end, owner_username, actor_role)})
        return rows
    return get_monthly_income_series(settings, owner_username, actor_role)


def get_cached_income_series(settings: Settings, period: str = "month", owner_username: str | None = None, actor_role: str = "admin") -> List[Dict]:
    clean_period = (period or "month").strip().lower()
    scope_key = (clean_period, (owner_username or "").strip(), (actor_role or "user").strip().lower())
    return _cached(settings, ("income_series", scope_key), lambda: get_income_series(settings, clean_period, owner_username, actor_role))  # type: ignore[return-value]
