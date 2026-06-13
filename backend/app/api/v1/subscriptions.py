from fastapi import APIRouter, Request

from backend.app.core.config import Settings
from backend.app.services.subscriptions import (
    clash_subscription_response,
    json_subscription_response,
    standard_subscription_response,
    subscription_landing_page_response,
)

router = APIRouter(tags=["subscriptions"])


@router.get("/sub/{node_id}/{sub_id:path}")
def standard_subscription(request: Request, node_id: int, sub_id: str, raw: int = 0, html: int = 0):
    settings: Settings = request.app.state.settings
    accept = request.headers.get("accept", "")
    if html or (not raw and "text/html" in accept.lower()):
        return subscription_landing_page_response(settings, node_id, sub_id)
    return standard_subscription_response(settings, node_id, sub_id)


@router.get("/json/{node_id}/{sub_id:path}")
def json_subscription(request: Request, node_id: int, sub_id: str):
    settings: Settings = request.app.state.settings
    return json_subscription_response(settings, node_id, sub_id)


@router.get("/clash/{node_id}/{sub_id:path}")
def clash_subscription(request: Request, node_id: int, sub_id: str):
    settings: Settings = request.app.state.settings
    return clash_subscription_response(settings, node_id, sub_id)
