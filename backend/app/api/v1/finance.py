from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from backend.app.core.config import Settings
from backend.app.core.deps import require_admin
from backend.app.services.finance import delete_financial_log, list_financial_logs, update_financial_log


router = APIRouter(prefix="/api/v1/finance", tags=["finance"])


class FinancialLogUpdatePayload(BaseModel):
    customer_name: str | None = None
    owner_username: str | None = None
    renew_price: str | None = None
    amount: float | None = None
    renew_days: int | None = None
    new_expiry: str | None = None
    created_at: str | None = None


@router.get("/logs")
def financial_logs(
    request: Request,
    page: int = 1,
    per_page: int = 20,
    keyword: str = "",
    owner_username: str = "",
    node_id: str | None = Query(default=None),
    date_from: str = "",
    date_to: str = "",
    username: str = Depends(require_admin),
):
    settings: Settings = request.app.state.settings
    clean_node_id = int(node_id) if str(node_id or "").strip() else None
    return {
        "success": True,
        "data": list_financial_logs(
            settings,
            page=page,
            per_page=per_page,
            keyword=keyword,
            owner_username=owner_username,
            node_id=clean_node_id,
            date_from=date_from,
            date_to=date_to,
        ),
    }


@router.put("/logs/{log_id}")
def update_log(request: Request, log_id: int, payload: FinancialLogUpdatePayload, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    data: dict[str, Any] = {key: value for key, value in payload.model_dump().items() if value is not None}
    return update_financial_log(settings, log_id, data, actor=username)


@router.delete("/logs/{log_id}")
def delete_log(request: Request, log_id: int, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return delete_financial_log(settings, log_id, actor=username)
