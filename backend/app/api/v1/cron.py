from fastapi import APIRouter, HTTPException, Request, status

from backend.app.core.config import Settings
from backend.app.core.deps import SESSION_LOGIN_KEY, SESSION_ROLE_KEY
from backend.app.services.notifications import run_webhook_check

router = APIRouter(prefix="/api/v1/cron", tags=["cron"])


def _cron_authorized(request: Request, settings: Settings) -> bool:
    if request.session.get(SESSION_LOGIN_KEY) and str(request.session.get(SESSION_ROLE_KEY) or "") == "admin":
        return True

    token = (
        request.query_params.get("token")
        or request.headers.get("X-Cron-Token")
        or request.headers.get("X-Subsentry-Cron-Token")
        or ""
    ).strip()
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    return bool(settings.cron_token and token and token == settings.cron_token)


def require_cron_access(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    if not _cron_authorized(request, settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return settings


@router.get("/check")
def check(request: Request):
    settings = require_cron_access(request)
    triggered_count, skipped_count, errors = run_webhook_check(settings, force=False)
    return {"status": "success", "triggered": triggered_count, "skipped": skipped_count, "errors": errors}


@router.post("/check")
def force_check(request: Request):
    settings = require_cron_access(request)
    triggered_count, skipped_count, errors = run_webhook_check(settings, force=True)
    return {
        "success": True,
        "message": f"已完成检测：触发 {triggered_count} 条，跳过 {skipped_count} 条",
        "triggered": triggered_count,
        "skipped": skipped_count,
        "errors": errors,
    }
