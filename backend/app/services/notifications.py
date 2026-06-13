import json
from datetime import datetime
from typing import Any, Dict, List, Tuple

import requests
from fastapi import HTTPException

from backend.app.core.config import Settings
from backend.app.db.database import execute, get_setting, query
from backend.app.services.common import (
    calculate_remaining_days,
    get_bool_setting,
    get_int_setting,
    is_now_within_push_window,
)
from backend.app.services.customers import get_customer, list_customers
from backend.app.services.logs import create_notification_log, update_notification_result
from backend.app.services.task_state import record_task_state


EVENT_TEMPLATE_KEYS = {
    "expiry_warning": "notification_template",
    "traffic_low": "notification_template_traffic_low",
    "customer_disabled": "notification_template_customer_disabled",
    "node_abnormal": "notification_template_node_abnormal",
}


def default_expiry_template() -> str:
    return (
        "### <font color=\"warning\">SubSentry 到期提醒</font>\n"
        "> 客户：<font color=\"info\">{name}</font>\n"
        "> 客户经理：{manager}\n"
        "> 节点：{node}\n"
        "> 续费价：{price}\n"
        "> 到期日：<font color=\"warning\">{expiry}</font>\n"
        "> 剩余：<font color=\"warning\">{rem}</font>\n"
        "> 状态：<font color=\"warning\">{status}</font>\n"
        "> 流量：{traffic}\n"
        "> 检测时间：<font color=\"comment\">{time}</font>\n\n"
        "请及时跟进续费。"
    )


def default_traffic_low_template() -> str:
    return (
        "### <font color=\"warning\">SubSentry 流量不足</font>\n"
        "> 客户：<font color=\"info\">{name}</font>\n"
        "> 客户经理：{manager}\n"
        "> 节点：{node}\n"
        "> 流量：<font color=\"warning\">{traffic}</font>\n"
        "> 到期日：{expiry}\n"
        "> 状态：<font color=\"warning\">{status}</font>\n"
        "> 检测时间：<font color=\"comment\">{time}</font>\n\n"
        "请检查套餐流量或提醒客户处理。"
    )


def default_customer_disabled_template() -> str:
    return (
        "### <font color=\"comment\">SubSentry 客户已停用</font>\n"
        "> 客户：<font color=\"info\">{name}</font>\n"
        "> 客户经理：{manager}\n"
        "> 节点：{node}\n"
        "> 到期日：{expiry}\n"
        "> 状态：<font color=\"comment\">{status}</font>\n"
        "> 检测时间：<font color=\"comment\">{time}</font>\n\n"
        "请确认是否为预期停用。"
    )


def default_node_abnormal_template() -> str:
    return (
        "### <font color=\"warning\">SubSentry 节点异常</font>\n"
        "> 节点：<font color=\"info\">{node}</font>\n"
        "> 状态：<font color=\"warning\">{status}</font>\n"
        "> 检测时间：<font color=\"comment\">{time}</font>\n\n"
        "请及时检查面板连通性。"
    )


def default_summary_template() -> str:
    return (
        "### <font color=\"warning\">{title}</font>\n"
        "> 检测时间：<font color=\"comment\">{time}</font>\n"
        "> 总计：<font color=\"warning\">{count}</font> 条\n"
        "> 已过期：<font color=\"warning\">{expired}</font> / 今日到期：<font color=\"warning\">{due_today}</font> / 7天内到期：<font color=\"info\">{warning}</font>\n"
        "> 流量不足：<font color=\"warning\">{traffic_low}</font> / 已停用：<font color=\"comment\">{disabled}</font>\n\n"
        "{detail}"
    )


def default_template_presets() -> Dict[str, str]:
    return {
        "notification_template": default_expiry_template(),
        "notification_template_traffic_low": default_traffic_low_template(),
        "notification_template_customer_disabled": default_customer_disabled_template(),
        "notification_template_node_abnormal": default_node_abnormal_template(),
        "notification_template_summary": default_summary_template(),
    }


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _webhook_for_customer(settings: Settings, customer: Dict[str, Any]) -> str:
    return (customer.get("webhook_url") or _default_webhook_url(settings)).strip()


def _default_webhook_url(settings: Settings) -> str:
    rows = query(settings, "SELECT value FROM system_settings WHERE `key` = ?", ("default_webhook_url",))
    if rows:
        return str(rows[0].get("value") or "").strip()
    return (settings.default_webhook_url or "").strip()


def _template_for_event(settings: Settings, event_type: str) -> str:
    key = EVENT_TEMPLATE_KEYS.get(event_type, "notification_template")
    fallback = default_template_presets().get(key, default_expiry_template())
    return get_setting(settings, key, "") or fallback


def _safe_format(template: str, payload_map: Dict[str, Any], fallback: str) -> str:
    try:
        return template.format(**payload_map)
    except Exception:
        return fallback.format(**payload_map)


def _remaining_text(rem_days: int, customer: Dict[str, Any] | None = None) -> str:
    customer = customer or {}
    if not customer.get("enable", True):
        return "已停用"
    if customer.get("is_unlimited_expiry"):
        return "无限期"
    if rem_days < 0:
        return f"已过期 {abs(rem_days)} 天"
    if rem_days == 0:
        return "今天到期"
    return f"剩余 {rem_days} 天"


def _status_text(rem_days: int, customer: Dict[str, Any]) -> str:
    if not customer.get("enable", True):
        return "客户已停用"
    if customer.get("is_unlimited_expiry"):
        return "无限期"
    if rem_days < 0:
        return "已过期"
    if rem_days == 0:
        return "今日到期"
    if rem_days <= 7:
        return "即将到期"
    return "正常"


def _traffic_text(customer: Dict[str, Any]) -> str:
    total = customer.get("traffic_total_display") or "-"
    used = customer.get("traffic_used_display") or "-"
    remaining = customer.get("traffic_remaining_display") or customer.get("traffic") or "-"
    if customer.get("is_unlimited_traffic"):
        return f"不限流量 / 已用 {used}" if used and used != "Unlimited" else "不限流量"
    return f"总额 {total} / 已用 {used} / 剩余 {remaining}"


def _customer_template_payload(customer: Dict[str, Any], rem_days: int, current_time_str: str) -> Dict[str, Any]:
    return {
        "name": customer.get("name") or "-",
        "manager": customer.get("manager") or "未分配",
        "node": customer.get("node") or "-",
        "price": customer.get("renew_price") or "-",
        "expiry": customer.get("expiry_display") or customer.get("expiry_date") or "-",
        "rem": _remaining_text(rem_days, customer),
        "status": _status_text(rem_days, customer),
        "traffic": _traffic_text(customer),
        "traffic_total": customer.get("traffic_total_display") or "-",
        "traffic_used": customer.get("traffic_used_display") or "-",
        "traffic_remaining": customer.get("traffic_remaining_display") or customer.get("traffic") or "-",
        "time": current_time_str,
    }


def _customer_event_type(customer: Dict[str, Any], rem_days: int) -> str:
    if not customer.get("enable", True):
        return "customer_disabled"
    remaining_gb = customer.get("traffic_remaining_gb")
    total_gb = customer.get("traffic_total_gb")
    if not customer.get("is_unlimited_traffic") and isinstance(remaining_gb, (int, float)):
        low_by_size = remaining_gb <= 5
        low_by_ratio = isinstance(total_gb, (int, float)) and total_gb > 0 and remaining_gb / total_gb <= 0.1
        if low_by_size or low_by_ratio:
            return "traffic_low"
    return "expiry_warning"


def _should_notify_customer(customer: Dict[str, Any], rem_days: int) -> bool:
    if not customer.get("enable", True):
        return True
    if _customer_event_type(customer, rem_days) == "traffic_low":
        return True
    if customer.get("is_unlimited_expiry"):
        return False
    return rem_days <= 7


def _post_webhook_with_log(
    settings: Settings,
    *,
    event_type: str,
    send_mode: str,
    webhook: str,
    payload: Dict[str, Any],
    customer: Dict[str, Any] | None = None,
    manager: str = "",
) -> bool:
    customer = customer or {}
    log_id = create_notification_log(
        settings,
        event_type=event_type,
        send_mode=send_mode,
        customer_id=str(customer.get("id") or ""),
        node_id=customer.get("node_id"),
        remote_email=customer.get("remote_email") or "",
        customer_name=customer.get("name") or "",
        manager=manager or customer.get("manager") or "",
        webhook_url=webhook,
        payload=payload,
    )
    if not webhook:
        update_notification_result(settings, log_id, status="failed", error_message="Webhook 为空")
        return False

    try:
        response = requests.post(
            webhook,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=8,
        )
        ok = response.status_code in (200, 201)
        update_notification_result(
            settings,
            log_id,
            status="success" if ok else "failed",
            response_status=response.status_code,
            response_text=response.text[:1000],
            error_message="" if ok else f"HTTP {response.status_code}",
        )
        return ok
    except Exception as exc:
        update_notification_result(settings, log_id, status="failed", error_message=str(exc))
        return False


def _post_group_webhook_with_logs(
    settings: Settings,
    *,
    event_type: str,
    send_mode: str,
    webhook: str,
    payload: Dict[str, Any],
    items: List[Tuple[Dict[str, Any], int, str]],
    manager: str = "",
) -> bool:
    log_ids = [
        create_notification_log(
            settings,
            event_type=event_type if event_type else item_event_type,
            send_mode=send_mode,
            customer_id=str(customer.get("id") or ""),
            node_id=customer.get("node_id"),
            remote_email=customer.get("remote_email") or "",
            customer_name=customer.get("name") or "",
            manager=manager or customer.get("manager") or "",
            webhook_url=webhook,
            payload=payload,
        )
        for customer, _, item_event_type in items
    ]
    if not webhook:
        for log_id in log_ids:
            update_notification_result(settings, log_id, status="failed", error_message="Webhook 为空")
        return False

    try:
        response = requests.post(
            webhook,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=8,
        )
        ok = response.status_code in (200, 201)
        for log_id in log_ids:
            update_notification_result(
                settings,
                log_id,
                status="success" if ok else "failed",
                response_status=response.status_code,
                response_text=response.text[:1000],
                error_message="" if ok else f"HTTP {response.status_code}",
            )
        return ok
    except Exception as exc:
        for log_id in log_ids:
            update_notification_result(settings, log_id, status="failed", error_message=str(exc))
        return False


def _build_single_payload(settings: Settings, customer: Dict[str, Any], rem_days: int, current_time_str: str, event_type: str) -> Dict[str, Any]:
    template = _template_for_event(settings, event_type)
    fallback_key = EVENT_TEMPLATE_KEYS.get(event_type, "notification_template")
    fallback = default_template_presets().get(fallback_key, default_expiry_template())
    markdown_content = _safe_format(template, _customer_template_payload(customer, rem_days, current_time_str), fallback)
    return {
        "msgtype": "markdown",
        "markdown": {"content": markdown_content},
        "text": f"[SubSentry] 客户 {customer.get('name', '-')} 通知",
    }


def _summary_detail_line(customer: Dict[str, Any], rem_days: int, event_type: str) -> str:
    event_label = {
        "traffic_low": "流量不足",
        "customer_disabled": "客户停用",
        "node_abnormal": "节点异常",
    }.get(event_type, "到期提醒")
    return (
        f"- <font color=\"info\">{customer.get('name', '-')}</font> | "
        f"经理:{customer.get('manager') or '未分配'} | "
        f"节点:{customer.get('node') or '-'} | "
        f"到期:{customer.get('expiry_display') or customer.get('expiry_date') or '-'} | "
        f"流量:{_traffic_text(customer)} | "
        f"<font color=\"warning\">{event_label}/{_remaining_text(rem_days, customer)}</font>"
    )


def _build_summary_payload(items: List[Tuple[Dict[str, Any], int, str]], current_time_str: str, max_detail_rows: int, title: str, settings: Settings) -> Dict[str, Any]:
    expired_count = sum(1 for _, rem, _ in items if rem < 0)
    due_today_count = sum(1 for _, rem, _ in items if rem == 0)
    warning_count = sum(1 for _, rem, event in items if 0 < rem <= 7 and event == "expiry_warning")
    traffic_low_count = sum(1 for _, _, event in items if event == "traffic_low")
    disabled_count = sum(1 for customer, _, event in items if event == "customer_disabled" or not customer.get("enable", True))

    detail_lines = [
        _summary_detail_line(customer, rem_days, event_type)
        for customer, rem_days, event_type in sorted(items, key=lambda x: (x[2], x[1], x[0].get("name") or ""))
    ]
    truncated = len(detail_lines) > max_detail_rows
    detail_body = "\n".join(detail_lines[:max_detail_rows])
    if truncated:
        detail_body += f"\n... 其余 {len(detail_lines) - max_detail_rows} 条已折叠"

    payload_map = {
        "title": title,
        "time": current_time_str,
        "count": len(items),
        "expired": expired_count,
        "due_today": due_today_count,
        "warning": warning_count,
        "traffic_low": traffic_low_count,
        "disabled": disabled_count,
        "detail": detail_body,
    }
    template = get_setting(settings, "notification_template_summary", "") or default_summary_template()
    markdown_content = _safe_format(template, payload_map, default_summary_template())
    return {
        "msgtype": "markdown",
        "markdown": {"content": markdown_content},
        "text": f"[SubSentry] {title} {len(items)} 条",
    }


def _mark_notified(settings: Settings, customer: Dict[str, Any], today_str: str) -> None:
    customer_id = str(customer.get("id") or "")
    if ":" in customer_id:
        return
    execute(settings, "UPDATE customers SET last_notified = ? WHERE id = ?", (today_str, customer_id))


def _already_notified_today(settings: Settings, customer: Dict[str, Any], event_type: str, today_str: str) -> bool:
    if customer.get("last_notified") == today_str:
        return True
    customer_id = str(customer.get("id") or "")
    if not customer_id:
        return False
    rows = query(
        settings,
        """
        SELECT id FROM notification_logs
        WHERE customer_id = ?
          AND status = 'success'
          AND (event_type = ? OR event_type = 'manager_summary')
          AND created_at LIKE ?
        LIMIT 1
        """,
        (customer_id, event_type, f"{today_str}%"),
    )
    return bool(rows)


def run_webhook_check(settings: Settings, force: bool = False) -> Tuple[int, int, List[str]]:
    now_dt = datetime.now()
    today_str = now_dt.strftime("%Y-%m-%d")
    current_time_str = _now_text()
    push_mode = (get_setting(settings, "push_mode", settings.default_push_mode) or settings.default_push_mode).strip()
    max_detail_rows = get_int_setting(settings, "max_detail_rows", settings.default_max_detail_rows)
    fixed_enabled = get_bool_setting(settings, "fixed_push_time_enabled", False)
    fixed_push_time = (get_setting(settings, "fixed_push_time", settings.default_fixed_push_time) or settings.default_fixed_push_time).strip()
    push_window_minutes = get_int_setting(settings, "push_time_window_minutes", settings.default_push_time_window_minutes)

    if push_mode not in ("per_customer", "summary", "hybrid", "manager_summary"):
        push_mode = settings.default_push_mode

    if fixed_enabled and not force and not is_now_within_push_window(now_dt, fixed_push_time, push_window_minutes):
        record_task_state(
            settings,
            category="notification",
            action="webhook_check",
            actor="system",
            status="success",
            summary="通知检查跳过：不在固定推送时间窗口",
            detail={
                "force": force,
                "fixed_push_time_enabled": fixed_enabled,
                "fixed_push_time": fixed_push_time,
                "push_time_window_minutes": push_window_minutes,
                "triggered": 0,
                "skipped": 0,
                "errors": [],
            },
        )
        return 0, 0, []

    customers = list_customers(settings, actor=settings.admin_user, actor_role="admin")
    triggered_count = 0
    skipped_count = 0
    errors: List[str] = []
    grouped: Dict[tuple[str, str], List[Tuple[Dict[str, Any], int, str]]] = {}

    def send_single(customer: Dict[str, Any], rem_days: int, event_type: str, mode: str = "per_customer") -> None:
        nonlocal triggered_count
        webhook = _webhook_for_customer(settings, customer)
        payload = _build_single_payload(settings, customer, rem_days, current_time_str, event_type)
        if _post_webhook_with_log(settings, event_type=event_type, send_mode=mode, webhook=webhook, payload=payload, customer=customer):
            _mark_notified(settings, customer, today_str)
            triggered_count += 1
        else:
            errors.append(f"客户 {customer.get('name', '-')} 通知发送失败")

    for customer in customers:
        rem_days = calculate_remaining_days(customer.get("expiry_date") or "")
        event_type = _customer_event_type(customer, rem_days)
        if not _should_notify_customer(customer, rem_days):
            continue
        if _already_notified_today(settings, customer, event_type, today_str):
            skipped_count += 1
            continue

        if push_mode == "per_customer":
            send_single(customer, rem_days, event_type)
            continue

        if push_mode == "hybrid" and (rem_days <= 0 or event_type != "expiry_warning"):
            send_single(customer, rem_days, event_type, mode="hybrid")
            continue

        webhook = _webhook_for_customer(settings, customer)
        manager_key = (customer.get("manager") or "未分配") if push_mode == "manager_summary" else ""
        grouped.setdefault((webhook, manager_key), []).append((customer, rem_days, event_type))

    for (webhook, manager), items in grouped.items():
        title = f"客户经理 {manager} 汇总预警" if manager else "到期与风险汇总预警"
        payload = _build_summary_payload(items, current_time_str, max_detail_rows, title, settings)
        send_mode = "manager_summary" if manager else "summary"
        ok = _post_group_webhook_with_logs(
            settings,
            event_type="manager_summary" if manager else "",
            send_mode=send_mode,
            webhook=webhook,
            payload=payload,
            items=items,
            manager=manager,
        )
        if ok:
            for customer, _, _ in items:
                _mark_notified(settings, customer, today_str)
            triggered_count += len(items)
        else:
            errors.append(f"{title} 发送失败")

    record_task_state(
        settings,
        category="notification",
        action="webhook_check",
        actor="system",
        status="failed" if errors else "success",
        summary=f"通知检查完成：触发 {triggered_count} 条，跳过 {skipped_count} 条，错误 {len(errors)} 条",
        detail={
            "force": force,
            "push_mode": push_mode,
            "fixed_push_time_enabled": fixed_enabled,
            "fixed_push_time": fixed_push_time,
            "push_time_window_minutes": push_window_minutes,
            "triggered": triggered_count,
            "skipped": skipped_count,
            "errors": errors,
        },
    )
    return triggered_count, skipped_count, errors


def test_customer_webhook(settings: Settings, customer_id: str, *, actor: str = "", actor_role: str = "admin") -> Dict[str, Any]:
    try:
        customer = get_customer(settings, str(customer_id), actor=actor, actor_role=actor_role)
    except HTTPException as exc:
        return {"success": False, "message": str(exc.detail)}

    rem_days = calculate_remaining_days(customer.get("expiry_date") or "")
    webhook = _webhook_for_customer(settings, customer)
    payload = _build_single_payload(settings, customer, rem_days, _now_text(), "expiry_warning")
    ok = _post_webhook_with_log(
        settings,
        event_type="test",
        send_mode="test",
        webhook=webhook,
        payload=payload,
        customer=customer,
    )
    return {"success": ok, "message": "测试成功，已发送并记录通知日志" if ok else "测试失败，已记录通知日志"}


def notify_node_abnormal(settings: Settings, node_id: int, error_message: str) -> bool:
    rows = query(settings, "SELECT * FROM catalog_nodes WHERE id = ?", (node_id,))
    if not rows:
        return False
    node = rows[0]
    payload_map = {
        "name": node.get("name") or "",
        "manager": "system",
        "node": node.get("name") or node.get("address") or f"node:{node_id}",
        "price": "-",
        "expiry": "-",
        "rem": "-",
        "traffic": "-",
        "traffic_total": "-",
        "traffic_used": "-",
        "traffic_remaining": "-",
        "status": error_message,
        "time": _now_text(),
    }
    template = get_setting(settings, "notification_template_node_abnormal", "") or default_node_abnormal_template()
    markdown_content = _safe_format(template, payload_map, default_node_abnormal_template())
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": markdown_content},
        "text": f"[SubSentry] 节点异常 {payload_map['node']}",
    }
    return _post_webhook_with_log(
        settings,
        event_type="node_abnormal",
        send_mode="system",
        webhook=_default_webhook_url(settings),
        payload=payload,
        customer={"node_id": node_id, "name": payload_map["node"], "node": payload_map["node"]},
    )
