from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.app.core.config import Settings
from backend.app.core.deps import SESSION_ROLE_KEY, require_login
from backend.app.services.dashboard import clear_dashboard_cache
from backend.app.services.customers import (
    bulk_assign_manager,
    bulk_update_customer_fields,
    create_customer,
    customer_audit_logs,
    customer_renewal_logs,
    delete_customer,
    get_customer,
    get_customer_subscription,
    list_customers,
    process_customer_renew,
    reset_customer_traffic,
    update_customer,
)
from backend.app.services.notifications import test_customer_webhook

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


class CustomerPayload(BaseModel):
    name: str | None = None
    manager: str | None = None
    node: str | None = None
    node_id: int | None = None
    remote_email: str | None = None
    expiry_date: str | None = None
    renew_price: str | None = None
    webhook_url: str | None = None
    duration_mode: str | None = None
    duration_days: int | None = None
    custom_expiry_date: str | None = None
    inbound_ids: list[int] | None = None
    total_gb: float | None = None
    traffic_multiplier: float | None = None
    enable: bool | None = None
    limit_ip: int | None = None


class RenewPayload(BaseModel):
    renew_days: int
    renew_price: str | None = None


class BulkAssignManagerPayload(BaseModel):
    customer_ids: list[str]
    manager: str


class BulkUpdateFieldsPayload(BaseModel):
    customer_ids: list[str]
    enable: bool | None = None
    total_gb: float | None = None
    traffic_multiplier: float | None = None
    limit_ip: int | None = None
    renew_price: str | None = None
    duration_mode: str | None = None
    duration_days: int | None = None
    custom_expiry_date: str | None = None
    expiry_date: str | None = None


class AuditQuery(BaseModel):
    action: str | None = None


@router.get("")
def customers(request: Request, keyword: str = "", node: str = "", node_id: int | None = None, manager: str = "", username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    rows = list_customers(settings, keyword=keyword, node_filter=node, node_id_filter=node_id, manager_filter=manager, actor=username, actor_role=actor_role)
    return {"success": True, "code": 0, "msg": "ok", "count": len(rows), "data": rows}


@router.post("")
def create(request: Request, payload: CustomerPayload, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    result = create_customer(settings, payload.model_dump(exclude_none=True), actor=username, actor_role=actor_role)
    clear_dashboard_cache()
    return result


@router.post("/bulk/assign-manager")
def bulk_assign(request: Request, payload: BulkAssignManagerPayload, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    result = bulk_assign_manager(settings, payload.customer_ids, payload.manager, actor=username, actor_role=actor_role)
    clear_dashboard_cache()
    return result


@router.post("/bulk/update-fields")
def bulk_update(request: Request, payload: BulkUpdateFieldsPayload, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    result = bulk_update_customer_fields(
        settings,
        payload.customer_ids,
        payload.model_dump(exclude={"customer_ids"}, exclude_none=True),
        actor=username,
        actor_role=actor_role,
    )
    clear_dashboard_cache()
    return result


@router.post("/{customer_id:path}/renew")
def renew(request: Request, customer_id: str, payload: RenewPayload, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    result = process_customer_renew(settings, customer_id, payload.renew_days, payload.renew_price or "", actor=username, actor_role=actor_role)
    clear_dashboard_cache()
    return result


@router.post("/{customer_id:path}/reset-traffic")
def reset_traffic(request: Request, customer_id: str, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    result = reset_customer_traffic(settings, customer_id, actor=username, actor_role=actor_role)
    clear_dashboard_cache()
    return result


@router.get("/{customer_id:path}/audit")
def audit(request: Request, customer_id: str, action: str | None = None, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    rows = customer_audit_logs(settings, customer_id, actor=username, actor_role=actor_role)
    if action:
        rows = [r for r in rows if r.get("action") == action]
    return {"success": True, "data": rows}


@router.post("/{customer_id:path}/test-webhook")
def webhook_test(request: Request, customer_id: str, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    return test_customer_webhook(settings, customer_id, actor=username, actor_role=actor_role)


@router.get("/{customer_id:path}/subscription")
def subscription(request: Request, customer_id: str, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    return get_customer_subscription(settings, customer_id, actor=username, actor_role=actor_role)


@router.get("/{customer_id:path}/renewals")
def renewals(request: Request, customer_id: str, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    return {"success": True, "data": customer_renewal_logs(settings, customer_id, actor=username, actor_role=actor_role)}


@router.get("/{customer_id:path}")
def detail(request: Request, customer_id: str, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    return {"success": True, "data": get_customer(settings, customer_id, actor=username, actor_role=actor_role)}


@router.put("/{customer_id:path}")
def edit(request: Request, customer_id: str, payload: CustomerPayload, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    result = update_customer(settings, customer_id, payload.model_dump(exclude_none=True), actor=username, actor_role=actor_role)
    clear_dashboard_cache()
    return result


@router.delete("/{customer_id:path}")
def remove(request: Request, customer_id: str, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    actor_role = str(request.session.get(SESSION_ROLE_KEY) or "user")
    result = delete_customer(settings, customer_id, actor=username, actor_role=actor_role)
    clear_dashboard_cache()
    return result
