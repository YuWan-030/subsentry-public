from fastapi import APIRouter, Depends, Request

from backend.app.core.config import Settings
from backend.app.core.deps import SESSION_ROLE_KEY, require_login
from backend.app.services.customers import list_customers
from backend.app.services.dashboard import clear_dashboard_cache, get_cached_dashboard_status, get_cached_income_series, get_cached_period_income

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(request: Request, period: str = "month", force: bool = False, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    if force:
        clear_dashboard_cache()
    summary = get_cached_dashboard_status(settings, username, actor_role, lambda: list_customers(settings, actor=username, actor_role=actor_role))
    summary["month_income"] = get_cached_period_income(settings, period, username, actor_role)
    return {"success": True, "data": summary}


@router.get("/status")
def status_summary(request: Request, force: bool = False, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    if force:
        clear_dashboard_cache()
    summary = get_cached_dashboard_status(settings, username, actor_role, lambda: list_customers(settings, actor=username, actor_role=actor_role))
    return {"success": True, "data": summary}


@router.get("/income")
def income_summary(request: Request, period: str = "month", force: bool = False, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    if force:
        clear_dashboard_cache()
    return {"success": True, "data": {"month_income": get_cached_period_income(settings, period, username, actor_role)}}


@router.get("/income-monthly")
def income_monthly(request: Request, period: str = "month", force: bool = False, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    if force:
        clear_dashboard_cache()
    return {"success": True, "data": {"series": get_cached_income_series(settings, period, username, actor_role)}}
