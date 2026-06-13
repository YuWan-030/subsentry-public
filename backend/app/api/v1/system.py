from fastapi import APIRouter, Depends, Request

from backend.app.core.config import Settings
from backend.app.core.deps import require_admin
from backend.app.services.system_health import get_system_health


router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/health")
def system_health(request: Request, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return {"success": True, "data": get_system_health(settings)}
