import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, Card, Col, Descriptions, Drawer, Empty, Form, Grid, Input, InputNumber, List, Modal, Popconfirm, Row, Select, Space, Switch, Table, Tag, Timeline, Typography } from "antd";
import type { Dayjs } from "dayjs";
import {
  fetchCustomerAuditByAction,
  fetchCustomerDetail,
  fetchCustomerRenewals,
  renewCustomer,
  resetCustomerTraffic,
  testCustomerWebhook,
  updateCustomer,
  type CustomerAuditRow,
  type CustomerRenewalRow,
  type CustomerRow,
} from "../api/customers";
import { fetchSettingsOptions } from "../api/settings";
import { useAuth } from "../api/auth";
import ExpiryModeField from "../components/ExpiryModeField";
import SubscriptionLinksModal from "../components/SubscriptionLinksModal";
import {
  buildExpiryPayload,
  computeDaysFromDate,
  DEFAULT_EXPIRY_MODE,
  formatDateValue,
  getRenewBaseDate,
  parseDateValue,
  type ExpiryMode,
} from "../utils/expiry";
import { fetchNotificationLogs, retryNotificationLog, type NotificationLogRow } from "../api/logs";
import { extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess, notifyDataLoaded } from "../utils/feedback";
import { formatIpLimit } from "../utils/display";

const { useBreakpoint } = Grid;
const RENEW_PRICE_PERIOD_OPTIONS = [
  { label: "月", value: "月" },
  { label: "季", value: "季" },
  { label: "年", value: "年" },
];

function UnitNumberInput({ value, onChange, unit, placeholder }: { value?: number; onChange?: (value: number | null) => void; unit: string; placeholder?: string }) {
  return (
    <div className="joined-unit-input">
      <InputNumber min={0} value={value} onChange={onChange} placeholder={placeholder} />
      <span className="joined-unit-label">{unit}</span>
    </div>
  );
}

type CustomerStatusMeta = {
  text: string;
  color: string;
};

type EditFormValues = {
  name: string;
  manager?: string;
  inbound_ids?: number[];
  total_gb?: number;
  traffic_multiplier?: number;
  limit_ip?: number;
  renew_price?: string;
  renew_price_amount?: string;
  renew_price_period?: "月" | "季" | "年";
  webhook_url?: string;
  enable?: boolean;
};

type RenewFormValues = {
  renew_price?: string;
};

const AUDIT_ACTIONS: Array<{ label: string; value?: string }> = [
  { label: "全部", value: undefined },
  { label: "新增", value: "新增" },
  { label: "修改", value: "修改" },
  { label: "删除", value: "删除" },
  { label: "续费", value: "续费" },
  { label: "重置流量", value: "重置流量" },
];

function getStatusMeta(customer: CustomerRow | null): CustomerStatusMeta {
  if (!customer) {
    return { text: "-", color: "default" };
  }

  switch (customer.status_level) {
    case "disabled":
      return { text: "未启用", color: "default" };
    case "unlimited":
      return { text: "无限期", color: "blue" };
    case "expired":
      return { text: customer.status_text || "已过期", color: "red" };
    case "today":
      return { text: customer.status_text || "今天到期", color: "orange" };
    case "warning":
      return { text: customer.status_text || "即将到期", color: "gold" };
    default:
      return { text: customer.status_text || "正常", color: "green" };
  }
}

function getRemainingDaysText(customer: CustomerRow | null) {
  if (!customer) {
    return "-";
  }
  if (!customer.enable || customer.status_level === "disabled") {
    return "未启用";
  }
  if (customer.is_unlimited_expiry) {
    return "无限期";
  }
  return String(customer.remaining_days ?? "-");
}

function getTrafficQuotaText(customer: CustomerRow | null) {
  if (!customer) {
    return "-";
  }
  if (customer.is_unlimited_traffic) {
    const used = customer.traffic_used_display && customer.traffic_used_display !== "Unlimited" ? customer.traffic_used_display : undefined;
    return used ? `不限流量 / 已用 ${used}` : "不限流量";
  }
  const total = customer.traffic_total_display || (typeof customer.traffic_total_gb === "number" ? `${customer.traffic_total_gb} GB` : "-");
  const used = customer.traffic_used_display || (typeof customer.traffic_used_gb === "number" ? `${customer.traffic_used_gb} GB` : "-");
  const remaining = customer.traffic_remaining_display || (typeof customer.traffic_remaining_gb === "number" ? `${customer.traffic_remaining_gb} GB` : "-");
  return `总额 ${total} / 已用 ${used} / 剩余 ${remaining}`;
}

function parseRenewPrice(value?: string | null): { amount: string; period: "月" | "季" | "年" } {
  const raw = String(value || "").trim();
  if (!raw || raw === "未设置") {
    return { amount: "", period: "月" };
  }
  const matched = raw.match(/^(.*)\/(月|季|年)$/);
  if (matched) {
    return { amount: matched[1].trim(), period: matched[2] as "月" | "季" | "年" };
  }
  return { amount: raw, period: "月" };
}

function buildRenewPrice(amount?: string, period?: "月" | "季" | "年") {
  const cleanAmount = String(amount || "").trim();
  return cleanAmount ? `${cleanAmount}/${period || "月"}` : "未设置";
}

export default function CustomerDetailPage() {
  const { user } = useAuth();
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const isAdmin = user?.role === "admin";
  const { id } = useParams();
  const navigate = useNavigate();
  const customerId = String(id || "");

  const [customer, setCustomer] = useState<CustomerRow | null>(null);
  const [audits, setAudits] = useState<CustomerAuditRow[]>([]);
  const [renewals, setRenewals] = useState<CustomerRenewalRow[]>([]);
  const [notificationLogs, setNotificationLogs] = useState<NotificationLogRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [renewOpen, setRenewOpen] = useState(false);
  const [subscriptionOpen, setSubscriptionOpen] = useState(false);
  const [webhookPanelOpen, setWebhookPanelOpen] = useState(false);
  const [auditAction, setAuditAction] = useState<string | undefined>(undefined);
  const [managerOptions, setManagerOptions] = useState<Array<{ label: string; value: string }>>([]);
  const [inboundOptions, setInboundOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [webhookResult, setWebhookResult] = useState<{ success: boolean; message: string } | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [renewSubmitting, setRenewSubmitting] = useState(false);
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const [webhookTesting, setWebhookTesting] = useState(false);
  const [editMode, setEditMode] = useState<ExpiryMode>(DEFAULT_EXPIRY_MODE);
  const [editDurationDays, setEditDurationDays] = useState<number | null>(0);
  const [editCustomDate, setEditCustomDate] = useState<Dayjs | null>(null);
  const [renewMode, setRenewMode] = useState<ExpiryMode>(DEFAULT_EXPIRY_MODE);
  const [renewDurationDays, setRenewDurationDays] = useState<number | null>(30);
  const [renewCustomDate, setRenewCustomDate] = useState<Dayjs | null>(null);
  const [editForm] = Form.useForm<EditFormValues>();
  const [renewForm] = Form.useForm<RenewFormValues>();
  const auditCacheRef = useRef(new Map<string, CustomerAuditRow[]>());
  const auditActionRef = useRef<string | undefined>(undefined);

  const auditCacheKey = useCallback((action?: string) => `${customerId}:${action || "all"}`, [customerId]);

  const clearAuditCache = useCallback(() => {
    Array.from(auditCacheRef.current.keys()).forEach((key) => {
      if (key.startsWith(`${customerId}:`)) {
        auditCacheRef.current.delete(key);
      }
    });
  }, [customerId]);

  const loadAuditRows = useCallback(async (action?: string, force = false) => {
    if (!customerId) {
      return;
    }

    const cacheKey = auditCacheKey(action);
    const cachedRows = auditCacheRef.current.get(cacheKey);
    if (!force && cachedRows) {
      setAudits(cachedRows);
      return;
    }

    setAuditLoading(true);
    try {
      const rows = await fetchCustomerAuditByAction(customerId, action);
      auditCacheRef.current.set(cacheKey, rows);
      setAudits(rows);
    } catch (error: any) {
      notifyActionError("customer-audit-load", extractErrorMessage(error, "加载审计记录失败"));
    } finally {
      setAuditLoading(false);
    }
  }, [auditCacheKey, customerId]);

  const loadData = useCallback(async (showSuccess = false, forceAudit = false) => {
    if (!customerId) {
      return;
    }

    if (forceAudit) {
      clearAuditCache();
    }
    setLoading(true);
    try {
      const [detail, renewalRows] = await Promise.all([
        fetchCustomerDetail(customerId),
        fetchCustomerRenewals(customerId),
      ]);
      setCustomer(detail);
      setRenewals(renewalRows);
      setInboundOptions(
        ((detail.inbounds || []) as Array<{ id: number; remark: string; protocol: string; port: number }>).map((inbound) => ({
          label: `${inbound.remark} | ${String(inbound.protocol || "").toUpperCase()} | ${inbound.port}`,
          value: inbound.id,
        })),
      );
      if (showSuccess) {
        notifyDataLoaded("customer-detail-load", "客户详情已刷新");
      }
    } catch (error: any) {
      notifyActionError("customer-detail-load", extractErrorMessage(error, "加载客户详情失败"));
    } finally {
      setLoading(false);
    }
    await loadAuditRows(auditActionRef.current, forceAudit);
  }, [clearAuditCache, customerId, loadAuditRows]);

  useEffect(() => {
    void loadData(false);
  }, [loadData]);

  useEffect(() => {
    auditActionRef.current = auditAction;
    void loadAuditRows(auditAction);
  }, [auditAction, loadAuditRows]);
  const loadNotificationLogs = async () => {
    if (!customerId) {
      return;
    }
    try {
      const result = await fetchNotificationLogs({ customer_id: customerId, page: 1, per_page: 10 });
      setNotificationLogs(result.items || []);
    } catch (error: any) {
      notifyActionError("customer-notification-logs", extractErrorMessage(error, "加载通知历史失败"));
    }
  };

  useEffect(() => {
    void loadNotificationLogs();
  }, [customerId]);

  const retryNotification = async (row: NotificationLogRow) => {
    try {
      notifyActionLoading("customer-notification-retry", `重试通知 #${row.id} 中...`);
      const result = await retryNotificationLog(row.id);
      notifyActionSuccess("customer-notification-retry", result.message || "通知已重试");
      await loadNotificationLogs();
    } catch (error: any) {
      notifyActionError("customer-notification-retry", extractErrorMessage(error, "重试通知失败"));
    }
  };

  const handleResetTraffic = async () => {
    try {
      setResetSubmitting(true);
      notifyActionLoading("customer-reset-traffic", "重置客户流量中...");
      const result = await resetCustomerTraffic(customerId);
      notifyActionSuccess("customer-reset-traffic", result.message || "客户流量已重置");
      await loadData(false, true);
    } catch (error: any) {
      notifyActionError("customer-reset-traffic", extractErrorMessage(error, "重置客户流量失败"));
    } finally {
      setResetSubmitting(false);
    }
  };

  useEffect(() => {
    const loadEditOptions = async () => {
      try {
        const options = await fetchSettingsOptions();
        setManagerOptions(options.managers.map((item) => ({ label: item.name, value: item.name })));
      } catch {
        // keep current manager text usable even if options fail
      }
    };
    void loadEditOptions();
  }, []);

  const statusMeta = useMemo(() => getStatusMeta(customer), [customer]);
  const remainingDaysText = useMemo(() => getRemainingDaysText(customer), [customer]);
  const trafficQuotaText = useMemo(() => getTrafficQuotaText(customer), [customer]);
  const inboundLabelMap = useMemo(() => new Map(inboundOptions.map((item) => [item.value, item.label])), [inboundOptions]);
  const renewBaseDate = useMemo(() => getRenewBaseDate(customer?.expiry_date, customer?.is_unlimited_expiry), [customer?.expiry_date, customer?.is_unlimited_expiry]);

  if (!customer) {
    return (
      <Card loading={loading} bordered={false} style={{ borderRadius: 24 }}>
        <Typography.Text>加载客户详情中...</Typography.Text>
      </Card>
    );
  }

  return (
    <div>
      <style>{`
        .customer-editor-form .ant-input,
        .customer-editor-form .ant-input-number,
        .customer-editor-form .ant-select-selector { height: 40px !important; border-radius: 10px !important; }
        .customer-editor-form .ant-input,
        .customer-editor-form .ant-input-number-input { line-height: 38px; }
        .customer-editor-form .ant-select-selector { display: flex !important; align-items: center; }
        .customer-editor-form .ant-select-selection-item,
        .customer-editor-form .ant-select-selection-placeholder { line-height: 38px !important; }
        .joined-unit-input { display: flex; width: 100%; }
        .joined-unit-input .ant-input-number { flex: 1 1 auto; min-width: 0; width: auto !important; border-radius: 10px 0 0 10px !important; }
        .joined-unit-label { width: 66px; height: 40px; flex: 0 0 66px; display: inline-flex; align-items: center; justify-content: center; margin-left: -1px; border: 1px solid var(--border-subtle); border-radius: 0 10px 10px 0; color: var(--text-sub); font-size: 14px; font-weight: 650; background: var(--surface-soft); }
        .joined-unit-input .ant-input-number:hover,
        .joined-unit-input .ant-input-number-focused { position: relative; z-index: 1; }
        .joined-price-input { display: flex; width: 100%; }
        .joined-price-input .ant-input { min-width: 0; border-radius: 10px 0 0 10px !important; }
        .joined-price-input .ant-select { width: 82px; flex: 0 0 82px; margin-left: -1px; }
        .joined-price-input .ant-select-selector { border-radius: 0 10px 10px 0 !important; }
        .joined-price-input .ant-input:hover,
        .joined-price-input .ant-input:focus,
        .joined-price-input .ant-select-focused .ant-select-selector { position: relative; z-index: 1; }
        .customer-detail-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
        .customer-detail-actions .detail-action-button { border-radius: 12px; }
        .customer-audit-card .ant-card-body { padding-right: 12px; }
        .customer-audit-scroll { max-height: min(50vh, 520px); overflow-y: auto; overflow-x: hidden; padding-right: 24px; scrollbar-gutter: stable; }
        .customer-audit-scroll .ant-timeline { margin-bottom: 0; }
        .customer-audit-row-head { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 12px; min-width: 0; }
        .customer-audit-row-action { min-width: 0; font-weight: 600; }
        .customer-audit-row-time { white-space: nowrap; color: #64748b; font-size: 12px; }
        @media (max-width: 767px) {
          .customer-detail-actions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); width: 100%; }
          .customer-detail-actions .detail-action-button { width: 100%; min-width: 0; padding-inline: 8px; }
          .customer-detail-actions .detail-action-renew { order: 1; }
          .customer-detail-actions .detail-action-edit { order: 2; }
          .customer-detail-actions .detail-action-reset { order: 3; }
          .customer-detail-actions .detail-action-subscription { order: 4; }
          .customer-detail-actions .detail-action-webhook { order: 5; }
          .customer-detail-actions .detail-action-refresh { order: 6; }
          .customer-detail-actions .detail-action-back { order: 7; grid-column: 1 / -1; }
          .customer-audit-scroll { max-height: 58vh; }
        }
      `}</style>
      <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", justifyContent: "space-between", alignItems: isMobile ? "stretch" : "flex-start", flexWrap: "wrap", gap: 16, marginBottom: 20 }}>
        <div>
          <Typography.Title level={isMobile ? 4 : 3} style={{ marginBottom: 4 }}>{customer.name}</Typography.Title>
          {!isMobile && <Typography.Text type="secondary">集中查看 3X-UI 客户数据与本地 ERP 字段，续费、Webhook、挂载入站调整都可以从这里直接完成。</Typography.Text>}
        </div>
        <div className="customer-detail-actions">
          <Button className="detail-action-button detail-action-back" onClick={() => navigate(-1)}>返回列表</Button>
          <Button className="detail-action-button detail-action-subscription" onClick={() => setSubscriptionOpen(true)}>订阅链接</Button>
          <Button
            className="detail-action-button detail-action-edit"
            onClick={() => {
              const renewPrice = parseRenewPrice(customer.renew_price);
              editForm.setFieldsValue({
                name: customer.name,
                manager: customer.manager,
                inbound_ids: customer.inbound_ids,
                total_gb: customer.total_gb,
                traffic_multiplier: customer.traffic_multiplier ?? 1,
                limit_ip: customer.limit_ip,
                renew_price_amount: renewPrice.amount,
                renew_price_period: renewPrice.period,
                webhook_url: customer.webhook_url,
                enable: customer.enable,
              });
              setEditMode("date");
              setEditCustomDate(parseDateValue(customer.expiry_date));
              setEditDurationDays(customer.is_unlimited_expiry ? 0 : customer.remaining_days ?? 0);
              setEditOpen(true);
            }}
          >
            编辑客户
          </Button>
          <Button
            type="primary"
            className="detail-action-button detail-action-renew"
            onClick={() => {
              renewForm.setFieldsValue({ renew_price: customer.renew_price });
              setRenewMode(DEFAULT_EXPIRY_MODE);
              setRenewDurationDays(30);
              setRenewCustomDate(null);
              setRenewOpen(true);
            }}
          >
            续费
          </Button>
          <Popconfirm
            title="确认重置该客户流量？"
            description="仅清空已用上传/下载流量，不改变总流量、到期时间、倍率和 IP 限制。"
            onConfirm={() => handleResetTraffic()}
            okText="确认重置"
            cancelText="取消"
          >
            <Button loading={resetSubmitting} className="detail-action-button detail-action-reset">重置流量</Button>
          </Popconfirm>
          <Button className="detail-action-button detail-action-refresh" onClick={() => void loadData(true)}>刷新详情</Button>
          <Button
            className="detail-action-button detail-action-webhook"
            loading={webhookTesting}
            onClick={async () => {
              try {
                setWebhookTesting(true);
                notifyActionLoading("customer-webhook-test", "Webhook 测试中...");
                const result = await testCustomerWebhook(customerId);
                notifyActionSuccess("customer-webhook-test", result.message);
                setWebhookResult(result);
                setWebhookPanelOpen(true);
              } catch (error: any) {
                const errorMessage = extractErrorMessage(error, "Webhook 测试失败");
                notifyActionError("customer-webhook-test", errorMessage);
                setWebhookResult({ success: false, message: errorMessage });
                setWebhookPanelOpen(true);
              } finally {
                setWebhookTesting(false);
              }
            }}
          >
            Webhook 测试
          </Button>
        </div>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={8}><Card bordered={false} style={{ borderRadius: 24 }}><Typography.Text type="secondary">当前状态</Typography.Text><div style={{ marginTop: 10 }}><Tag color={statusMeta.color}>{statusMeta.text}</Tag></div></Card></Col>
        <Col xs={24} md={8}><Card bordered={false} style={{ borderRadius: 24 }}><Typography.Text type="secondary">到期时间</Typography.Text><Typography.Title level={3} style={{ marginTop: 8, marginBottom: 0 }}>{customer.expiry_display || "-"}</Typography.Title></Card></Col>
        <Col xs={24} md={8}><Card bordered={false} style={{ borderRadius: 24 }}><Typography.Text type="secondary">续费价格</Typography.Text><Typography.Title level={3} style={{ marginTop: 8, marginBottom: 0 }}>{customer.renew_price || "未设置"}</Typography.Title></Card></Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={13}>
          <Card title="客户资料" bordered={false} style={{ borderRadius: 24, height: "100%" }}>
            <Descriptions column={1} size="middle">
              <Descriptions.Item label="客户名称">{customer.name}</Descriptions.Item>
              <Descriptions.Item label="3X-UI 订阅ID">{customer.sub_id || "-"}</Descriptions.Item>
              <Descriptions.Item label="所属节点">{customer.node}</Descriptions.Item>
              <Descriptions.Item label="客户经理">{customer.manager || "未分配"}</Descriptions.Item>
              <Descriptions.Item label="挂载入站">
                {Array.isArray(customer.inbound_ids) && customer.inbound_ids.length ? (
                  <Space wrap>{customer.inbound_ids.map((inboundId) => <Tag key={inboundId}>{inboundLabelMap.get(inboundId) || `入站 ${inboundId}`}</Tag>)}</Space>
                ) : "-"}
              </Descriptions.Item>
              <Descriptions.Item label="到期时间">{customer.expiry_display || "-"}</Descriptions.Item>
              <Descriptions.Item label="剩余天数">{remainingDaysText}</Descriptions.Item>
              <Descriptions.Item label="流量额度">{trafficQuotaText}</Descriptions.Item>
              <Descriptions.Item label="流量扣减倍率">{customer.traffic_multiplier ? `${customer.traffic_multiplier} 倍` : "1 倍"}</Descriptions.Item>
              <Descriptions.Item label="IP 限制">{formatIpLimit(customer.limit_ip)}</Descriptions.Item>
              <Descriptions.Item label="启用状态">{customer.enable ? "启用" : "停用"}</Descriptions.Item>
              <Descriptions.Item label="Webhook">{customer.webhook_url || "使用全局默认 Webhook"}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} xl={11}>
          <Card
            loading={auditLoading}
            className="customer-audit-card"
            bordered={false}
            style={{ borderRadius: 24, height: "100%" }}
            title={<div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}><span style={{ fontWeight: 600 }}>审计记录</span><Space wrap>{AUDIT_ACTIONS.map((item) => <Button key={String(item.value ?? "all")} type={auditAction === item.value ? "primary" : "default"} size="small" onClick={() => setAuditAction(item.value)}>{item.label}</Button>)}</Space></div>}
          >
            <div className="customer-audit-scroll">
              {audits.length ? (
                <Timeline items={audits.map((item) => ({ color: item.action === "删除" ? "red" : item.action === "新增" ? "blue" : item.action === "续费" ? "green" : item.action === "重置流量" ? "purple" : "gray", children: <div style={{ paddingBottom: 8 }}><div className="customer-audit-row-head"><span className="customer-audit-row-action">{item.action}</span><span className="customer-audit-row-time">{item.created_at}</span></div><div style={{ color: "#64748b", fontSize: 12, marginTop: 2 }}>操作人：{item.actor}</div><div style={{ marginTop: 8, lineHeight: 1.7 }}>{item.change_summary}</div></div> }))} />
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无审计记录" />
              )}
            </div>
          </Card>
        </Col>
      </Row>

      <Card title="续费记录" bordered={false} style={{ marginTop: 16, borderRadius: 24 }}>
        {isMobile ? (
          <List
            dataSource={renewals}
            renderItem={(item) => (
              <List.Item>
                <Space direction="vertical" size={4} style={{ width: "100%" }}>
                  <Space wrap><Tag color="green">续费 {item.renew_days} 天</Tag><Typography.Text type="secondary">{item.created_at}</Typography.Text></Space>
                  <Typography.Text>到期：{item.old_expiry} {"->"} {item.new_expiry}</Typography.Text>
                  <Typography.Text type="secondary">操作人：{item.actor} / 价格：{item.renew_price}</Typography.Text>
                </Space>
              </List.Item>
            )}
          />
        ) : (
          <Table rowKey="id" loading={loading} pagination={false} dataSource={renewals} scroll={{ x: 760 }} columns={[
            { title: "时间", dataIndex: "created_at", key: "created_at" },
            { title: "操作人", dataIndex: "actor", key: "actor" },
            { title: "续费天数", dataIndex: "renew_days", key: "renew_days" },
            { title: "旧到期", dataIndex: "old_expiry", key: "old_expiry" },
            { title: "新到期", dataIndex: "new_expiry", key: "new_expiry" },
            { title: "价格", dataIndex: "renew_price", key: "renew_price" },
          ]} />
        )}
      </Card>

      <Card title="通知历史" bordered={false} style={{ marginTop: 16, borderRadius: 24 }}>
        {isMobile ? (
          <List
            dataSource={notificationLogs}
            renderItem={(row) => (
              <List.Item>
                <Space direction="vertical" size={4} style={{ width: "100%" }}>
                  <Space wrap>
                    <Tag>{row.event_type}</Tag>
                    <Tag color={row.status === "success" ? "green" : row.status === "failed" ? "red" : "blue"}>{row.status === "success" ? "成功" : row.status === "failed" ? "失败" : "等待中"}</Tag>
                    <Typography.Text type="secondary">{row.created_at}</Typography.Text>
                  </Space>
                  <Typography.Text type="secondary">模式：{row.send_mode} / 响应：{row.response_status || "-"}</Typography.Text>
                  {row.error_message ? <Typography.Text type="danger">{row.error_message}</Typography.Text> : null}
                  <Button size="small" disabled={row.status !== "failed"} onClick={() => void retryNotification(row)}>重试</Button>
                </Space>
              </List.Item>
            )}
          />
        ) : (
          <Table rowKey="id" pagination={false} dataSource={notificationLogs} scroll={{ x: 900 }} columns={[
            { title: "时间", dataIndex: "created_at", key: "created_at" },
            { title: "事件", dataIndex: "event_type", key: "event_type" },
            { title: "模式", dataIndex: "send_mode", key: "send_mode" },
            { title: "状态", dataIndex: "status", key: "status", render: (value) => <Tag color={value === "success" ? "green" : value === "failed" ? "red" : "blue"}>{value === "success" ? "成功" : value === "failed" ? "失败" : "等待中"}</Tag> },
            { title: "响应", dataIndex: "response_status", key: "response_status", render: (value) => value || "-" },
            { title: "错误", dataIndex: "error_message", key: "error_message", ellipsis: true, render: (value) => value || "-" },
            {
              title: "操作",
              key: "action",
              align: "right",
              render: (_, row) => <Button size="small" disabled={row.status !== "failed"} onClick={() => void retryNotification(row)}>重试</Button>,
            },
          ]} />
        )}
      </Card>

      <Modal
        open={editOpen}
        title="编辑客户"
        onCancel={() => setEditOpen(false)}
        confirmLoading={editSubmitting}
        onOk={async () => {
          const values = await editForm.validateFields();
          const renewPrice = buildRenewPrice(values.renew_price_amount, values.renew_price_period);
          try {
            setEditSubmitting(true);
            notifyActionLoading("customer-detail-update", "保存客户中...");
            await updateCustomer(customerId, {
              name: values.name,
              manager: isAdmin ? values.manager : undefined,
              inbound_ids: values.inbound_ids,
              total_gb: values.total_gb,
              traffic_multiplier: values.traffic_multiplier,
              limit_ip: values.limit_ip,
              renew_price: renewPrice,
              webhook_url: values.webhook_url,
              enable: values.enable,
              ...buildExpiryPayload(editMode, editDurationDays, editCustomDate),
            });
            notifyActionSuccess("customer-detail-update", "客户已更新");
            setEditOpen(false);
            await loadData(false, true);
          } catch (error: any) {
            notifyActionError("customer-detail-update", extractErrorMessage(error, "更新失败"));
          } finally {
            setEditSubmitting(false);
          }
        }}
        destroyOnClose
        width={isMobile ? "calc(100vw - 16px)" : 900}
        style={isMobile ? { top: 8, paddingBottom: 8 } : undefined}
        styles={{
          content: isMobile
            ? { maxHeight: "calc(100dvh - 16px)", display: "flex", flexDirection: "column", overflow: "hidden" }
            : { overflow: "hidden" },
          header: { flexShrink: 0 },
          body: {
            paddingTop: 16,
            maxHeight: isMobile ? "calc(100dvh - 156px)" : "min(72vh, 680px)",
            overflowY: "auto",
            overflowX: "hidden",
            flex: isMobile ? "1 1 auto" : undefined,
            minHeight: 0,
          },
          footer: { flexShrink: 0 },
        }}
      >
        <Form form={editForm} layout="vertical" className="customer-editor-form">
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item name="name" label="客户名称" rules={[{ required: true, message: "请输入客户名称" }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              {isAdmin ? (
                <Form.Item name="manager" label="客户经理">
                  <Select options={managerOptions} allowClear />
                </Form.Item>
              ) : (
                <Form.Item label="客户经理">
                  <Input value={customer.manager || user?.nickname || user?.username || ""} disabled />
                </Form.Item>
              )}
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="inbound_ids" label="挂载入站" rules={[{ required: true, message: "请至少选择一个入站" }]}>
                <Select mode="multiple" options={inboundOptions} maxTagCount="responsive" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="enable" label="启用状态" valuePropName="checked">
                <Switch checkedChildren="启用" unCheckedChildren="停用" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="到期设置">
                <ExpiryModeField
                  mode={editMode}
                  onModeChange={setEditMode}
                  durationDays={editDurationDays}
                  onDurationDaysChange={(value) => setEditDurationDays(value ?? null)}
                  targetDate={editCustomDate}
                  onTargetDateChange={setEditCustomDate}
                  previewLabel="保存后到期日"
                  baseDateText="今天"
                  zeroDaysText="0 表示无限期"
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="用量限制">
                <Space direction="vertical" size={10} style={{ width: "100%" }}>
                  <Form.Item name="total_gb" noStyle>
                    <UnitNumberInput unit="GB" placeholder="0 表示不限流量" />
                  </Form.Item>
                  <Form.Item name="traffic_multiplier" noStyle>
                    <UnitNumberInput unit="倍" placeholder="5 表示按 5 倍扣减" />
                  </Form.Item>
                  <Form.Item name="limit_ip" noStyle>
                    <UnitNumberInput unit="IP" placeholder="0 表示不限制 IP" />
                  </Form.Item>
                </Space>
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="续费价格">
                <div className="joined-price-input">
                  <Form.Item name="renew_price_amount" noStyle>
                    <Input placeholder="例如：40" />
                  </Form.Item>
                  <Form.Item name="renew_price_period" noStyle>
                    <Select options={RENEW_PRICE_PERIOD_OPTIONS} />
                  </Form.Item>
                </div>
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="webhook_url" label="Webhook">
                <Input placeholder="留空则使用全局默认 Webhook" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        open={renewOpen}
        title="客户续费"
        onCancel={() => setRenewOpen(false)}
        confirmLoading={renewSubmitting}
        onOk={async () => {
          const values = await renewForm.validateFields();
          const renewDays = renewMode === "date" ? computeDaysFromDate(renewCustomDate, renewBaseDate) ?? 0 : renewDurationDays ?? 0;
          try {
            setRenewSubmitting(true);
            notifyActionLoading("customer-renew", "客户续费中...");
            const result = await renewCustomer(customerId, { renew_days: renewDays, renew_price: values.renew_price });
            notifyActionSuccess("customer-renew", result.message || "续费成功");
            setRenewOpen(false);
            await loadData(false, true);
          } catch (error: any) {
            notifyActionError("customer-renew", extractErrorMessage(error, "续费失败"));
          } finally {
            setRenewSubmitting(false);
          }
        }}
        destroyOnClose
      >
        <Form form={renewForm} layout="vertical">
          <Form.Item label="续费模式">
            <ExpiryModeField
              mode={renewMode}
              onModeChange={setRenewMode}
              durationDays={renewDurationDays}
              onDurationDaysChange={(value) => setRenewDurationDays(value ?? null)}
              targetDate={renewCustomDate}
              onTargetDateChange={(value) => {
                setRenewCustomDate(value);
                if (value) {
                  setRenewDurationDays(computeDaysFromDate(value, renewBaseDate) ?? 0);
                }
              }}
              baseDate={renewBaseDate}
              baseDateLabel="续费基准"
              baseDateText={renewBaseDate.format("YYYY-MM-DD")}
              previewLabel="续费后到期日"
            />
          </Form.Item>
          <Typography.Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
            当前客户到期日：{customer.expiry_display || "-"}，续费基准：{renewBaseDate.format("YYYY-MM-DD")}。
          </Typography.Text>
          <Form.Item name="renew_price" label="续费价格"><Input /></Form.Item>
        </Form>
      </Modal>

      <Drawer title="Webhook 测试结果" open={webhookPanelOpen} onClose={() => setWebhookPanelOpen(false)} width={isMobile ? "100%" : 420}>
        <Typography.Text>{webhookResult?.message || "暂无结果"}</Typography.Text>
      </Drawer>
      <SubscriptionLinksModal customerId={customerId} open={subscriptionOpen} onClose={() => setSubscriptionOpen(false)} />
    </div>
  );
}
