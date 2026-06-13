from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend.app.core.config import Settings
from backend.app.core.deps import require_admin, require_login
from backend.app.db.database import get_setting, upsert_setting
from backend.app.services.common import get_bool_setting, get_int_setting
from backend.app.services.logs import write_activity_log
from backend.app.services.notifications import default_template_presets
from backend.app.services.settings import (
    add_catalog_item,
    create_node,
    delete_catalog_item,
    delete_node,
    fetch_node_subscription_settings,
    get_settings_options,
    probe_all_nodes,
    probe_existing_node,
    test_node_connection,
    update_node,
)
from backend.app.services.subscriptions import (
    LOCAL_SUBSCRIPTION_BASE_URL_KEY,
    LOCAL_SUBSCRIPTION_ENABLED_KEY,
    LOCAL_SUBSCRIPTION_PORT_KEY,
    LOCAL_SUBSCRIPTION_TITLE_KEY,
    local_subscription_config,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class TemplatePayload(BaseModel):
    notification_template: str
    notification_template_traffic_low: str | None = None
    notification_template_customer_disabled: str | None = None
    notification_template_node_abnormal: str | None = None
    notification_template_summary: str | None = None


class NotificationConfigPayload(BaseModel):
    push_mode: str
    max_detail_rows: int
    fixed_push_time: str
    fixed_push_time_enabled: bool = False
    push_time_window_minutes: int


class SiteConfigPayload(BaseModel):
    announcement_enabled: bool = False
    announcement_text: str | None = None
    icp_number: str | None = None
    icp_link: str | None = None


class LocalSubscriptionConfigPayload(BaseModel):
    enabled: bool = False
    base_url: str | None = None
    port: int = 10883
    title: str | None = None


class NamePayload(BaseModel):
    name: str


class NodePayload(BaseModel):
    name: str
    scheme: str = "https"
    address: str
    port: int = 443
    base_path: str = "/"
    api_token: str
    allow_insecure: bool = False
    subscription_scheme: str | None = None
    subscription_address: str | None = None
    subscription_port: int | None = None
    subscription_sub_path: str | None = None
    subscription_json_path: str | None = None
    subscription_clash_path: str | None = None


def _site_config_data(settings: Settings) -> dict:
    return {
        "announcement_enabled": get_bool_setting(settings, "site_announcement_enabled", False),
        "announcement_text": get_setting(settings, "site_announcement_text", ""),
        "icp_number": get_setting(settings, "site_icp_number", ""),
        "icp_link": get_setting(settings, "site_icp_link", ""),
    }


@router.get("/site-public")
def site_public(request: Request):
    settings: Settings = request.app.state.settings
    return {"success": True, "data": _site_config_data(settings)}


@router.get("/site-config")
def site_config(request: Request, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return {"success": True, "data": _site_config_data(settings)}


@router.post("/site-config")
def update_site_config(request: Request, payload: SiteConfigPayload, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    announcement_text = (payload.announcement_text or "").strip()
    icp_number = (payload.icp_number or "").strip()
    icp_link = (payload.icp_link or "").strip()

    upsert_setting(settings, "site_announcement_enabled", "1" if payload.announcement_enabled else "0")
    upsert_setting(settings, "site_announcement_text", announcement_text)
    upsert_setting(settings, "site_icp_number", icp_number)
    upsert_setting(settings, "site_icp_link", icp_link)
    write_activity_log(
        settings,
        category="settings",
        action="update_site_config",
        actor=username,
        summary="更新站点展示设置",
        detail={"announcement_enabled": payload.announcement_enabled, "icp_number": icp_number, "icp_link": icp_link},
        ip_address=request.client.host if request.client else "",
    )
    return {"success": True, "message": "站点展示设置已保存"}


@router.get("/local-subscription-config")
def local_subscription_settings(request: Request, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return {"success": True, "data": local_subscription_config(settings)}


@router.post("/local-subscription-config")
def update_local_subscription_settings(request: Request, payload: LocalSubscriptionConfigPayload, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    base_url = (payload.base_url or settings.public_subscription_base_url).strip().rstrip("/")
    title = (payload.title or "SubSentry").strip()
    port = int(payload.port or 10883)

    if payload.enabled and not base_url:
        return {"success": False, "message": "本地订阅公开链接不能为空"}
    if payload.enabled and not title:
        return {"success": False, "message": "订阅 Title 不能为空"}
    if port < 1 or port > 65535:
        return {"success": False, "message": "端口必须在 1-65535 之间"}

    upsert_setting(settings, LOCAL_SUBSCRIPTION_ENABLED_KEY, "1" if payload.enabled else "0")
    upsert_setting(settings, LOCAL_SUBSCRIPTION_BASE_URL_KEY, base_url or settings.public_subscription_base_url)
    upsert_setting(settings, LOCAL_SUBSCRIPTION_PORT_KEY, str(port))
    upsert_setting(settings, LOCAL_SUBSCRIPTION_TITLE_KEY, title or "SubSentry")
    write_activity_log(
        settings,
        category="settings",
        action="update_local_subscription",
        actor=username,
        summary="更新本地订阅服务设置",
        detail={"enabled": payload.enabled, "base_url": base_url, "port": port, "title": title},
        ip_address=request.client.host if request.client else "",
    )
    return {"success": True, "message": "本地订阅服务设置已保存", "data": local_subscription_config(settings)}


@router.get("/notification-config")
def notification_config(request: Request, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    return {
        "success": True,
        "push_mode": get_setting(settings, "push_mode", settings.default_push_mode),
        "max_detail_rows": get_int_setting(settings, "max_detail_rows", settings.default_max_detail_rows),
        "fixed_push_time": get_setting(settings, "fixed_push_time", settings.default_fixed_push_time),
        "fixed_push_time_enabled": get_bool_setting(settings, "fixed_push_time_enabled", False),
        "push_time_window_minutes": get_int_setting(settings, "push_time_window_minutes", settings.default_push_time_window_minutes),
    }


@router.get("/options")
def options(request: Request, username: str = Depends(require_login)):
    settings: Settings = request.app.state.settings
    return get_settings_options(settings)


@router.get("/notification-template")
def notification_template(request: Request, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    presets = default_template_presets()
    return {
        "success": True,
        "notification_template": get_setting(settings, "notification_template", presets["notification_template"]),
        "notification_template_traffic_low": get_setting(settings, "notification_template_traffic_low", presets["notification_template_traffic_low"]),
        "notification_template_customer_disabled": get_setting(settings, "notification_template_customer_disabled", presets["notification_template_customer_disabled"]),
        "notification_template_node_abnormal": get_setting(settings, "notification_template_node_abnormal", presets["notification_template_node_abnormal"]),
        "notification_template_summary": get_setting(settings, "notification_template_summary", presets["notification_template_summary"]),
        "presets": presets,
    }


@router.post("/notification-template")
def update_template(request: Request, payload: TemplatePayload, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    template = payload.notification_template.strip()
    if not template:
        return {"success": False, "message": "模板内容不能为空"}
    upsert_setting(settings, "notification_template", template)
    for key in ("notification_template_traffic_low", "notification_template_customer_disabled", "notification_template_node_abnormal", "notification_template_summary"):
        value = (getattr(payload, key) or "").strip()
        if value:
            upsert_setting(settings, key, value)
    return {"success": True, "message": "通知模板已保存"}


@router.post("/notification-config")
def update_config(request: Request, payload: NotificationConfigPayload, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    if payload.push_mode not in ("per_customer", "summary", "hybrid", "manager_summary"):
        return {"success": False, "message": "推送模式不合法"}
    if payload.max_detail_rows < 5 or payload.max_detail_rows > 200:
        return {"success": False, "message": "汇总详情行数需要在 5-200 之间"}
    if payload.push_time_window_minutes < 1 or payload.push_time_window_minutes > 180:
        return {"success": False, "message": "推送时间窗口需要在 1-180 分钟之间"}

    upsert_setting(settings, "push_mode", payload.push_mode)
    upsert_setting(settings, "max_detail_rows", str(payload.max_detail_rows))
    upsert_setting(settings, "fixed_push_time", payload.fixed_push_time)
    upsert_setting(settings, "fixed_push_time_enabled", "1" if payload.fixed_push_time_enabled else "0")
    upsert_setting(settings, "push_time_window_minutes", str(payload.push_time_window_minutes))
    return {"success": True, "message": "推送策略已保存"}


@router.post("/nodes")
def add_node(request: Request, payload: NodePayload, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    result = create_node(settings, payload.model_dump())
    write_activity_log(settings, category="node", action="create", actor=username, target_type="node", target_id=str(result.get("id") or ""), target_name=payload.name, summary=f"新增节点：{payload.name}")
    return result


@router.post("/nodes/test")
def test_node(request: Request, payload: NodePayload, username: str = Depends(require_admin)):
    return test_node_connection(payload.model_dump())


@router.post("/nodes/subscription-settings")
def read_subscription_settings(request: Request, payload: NodePayload, username: str = Depends(require_admin)):
    return fetch_node_subscription_settings(payload.model_dump())


@router.put("/nodes/{item_id}")
def edit_node(request: Request, item_id: int, payload: NodePayload, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    result = update_node(settings, item_id, payload.model_dump())
    write_activity_log(settings, category="node", action="update", actor=username, target_type="node", target_id=str(item_id), target_name=payload.name, summary=f"更新节点：{payload.name}", detail=payload.model_dump(exclude={"api_token"}))
    return result


@router.delete("/nodes/{item_id}")
def remove_node(request: Request, item_id: int, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    result = delete_node(settings, item_id)
    write_activity_log(settings, category="node", action="delete", actor=username, target_type="node", target_id=str(item_id), summary=f"删除节点：{item_id}")
    return result


@router.post("/nodes/probe-all")
def probe_nodes(request: Request, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    result = probe_all_nodes(settings, notify_on_transition=True, actor=username)
    write_activity_log(
        settings,
        category="node",
        action="probe_all",
        actor=username,
        target_type="node",
        summary="批量探测全部节点",
        detail={"total": result.get("total"), "online": result.get("online"), "offline": result.get("offline")},
    )
    return result


@router.post("/nodes/{item_id}/probe")
def probe_node(request: Request, item_id: int, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    try:
        result = probe_existing_node(settings, item_id)
        write_activity_log(settings, category="node", action="probe", actor=username, target_type="node", target_id=str(item_id), summary=f"探测节点：{item_id}", detail=result)
        return result
    except Exception as exc:
        write_activity_log(settings, category="node", action="probe", actor=username, target_type="node", target_id=str(item_id), status="failed", summary=f"节点探测失败：{item_id}", detail=str(exc))
        raise


@router.post("/managers")
def add_manager(request: Request, payload: NamePayload, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    ok, message = add_catalog_item(settings, "catalog_managers", payload.name)
    return {"success": ok, "message": message}


@router.delete("/managers/{item_id}")
def remove_manager(request: Request, item_id: int, username: str = Depends(require_admin)):
    settings: Settings = request.app.state.settings
    ok, message = delete_catalog_item(settings, "catalog_managers", item_id)
    return {"success": ok, "message": message}
