import json
from datetime import datetime
from typing import Any, Dict

from backend.app.core.config import Settings
from backend.app.db.database import get_setting, upsert_setting


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _task_state_key(category: str, action: str) -> str:
    return f"task_state:{category}:{action}"


def record_task_state(
    settings: Settings,
    *,
    category: str,
    action: str,
    actor: str = "system",
    status: str,
    summary: str,
    detail: Any = None,
) -> Dict[str, Any]:
    state = {
        "category": category,
        "action": action,
        "actor": actor,
        "status": status,
        "summary": summary,
        "detail": detail or {},
        "created_at": _now_text(),
    }
    upsert_setting(settings, _task_state_key(category, action), json.dumps(state, ensure_ascii=False))
    return state


def read_task_state(settings: Settings, category: str, action: str) -> Dict[str, Any] | None:
    raw = get_setting(settings, _task_state_key(category, action), "")
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None
