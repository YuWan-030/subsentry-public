from fastapi import APIRouter, Depends, Request

from backend.app.core.config import Settings
from backend.app.core.deps import SESSION_ROLE_KEY, require_admin, require_login
from backend.app.services.customers import get_customer
from backend.app.services.logs import list_activity_categories, list_activity_logs, list_notification_logs, retry_notification

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


@router.get("/activity")
def activity_logs(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    category: str = "",
    keyword: str = "",
    username: str = Depends(require_admin),
):
    settings: Settings = request.app.state.settings
    return {"success": True, "data": list_activity_logs(settings, page=page, per_page=per_page, category=category, keyword=keyword)}


@router.get("/activity/categories")
def activity_categories(request: Request, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return {"success": True, "data": list_activity_categories(settings)}


@router.get("/notifications")
def notification_logs(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    status: str = "",
    event_type: str = "",
    customer_id: str = "",
    username: str = Depends(require_login),
):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    if actor_role != "admin":
        if not customer_id:
            return {"success": False, "message": "普通用户只能查看单客户通知历史"}
        get_customer(settings, customer_id, actor=username, actor_role=actor_role)
    return {"success": True, "data": list_notification_logs(settings, page=page, per_page=per_page, status=status, event_type=event_type, customer_id=customer_id)}


@router.post("/notifications/{log_id}/retry")
def retry_notification_log(request: Request, log_id: int, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return retry_notification(settings, log_id)
