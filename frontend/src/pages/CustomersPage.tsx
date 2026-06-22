import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useDeferredValue } from "react";
import { Button, Card, Checkbox, Col, Dropdown, Form, Grid, Input, InputNumber, List, Modal, Popconfirm, Row, Select, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { MenuProps } from "antd";
import { ArrowRightOutlined, ClusterOutlined, DeleteOutlined, LinkOutlined, MoreOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, SyncOutlined, UserOutlined, WalletOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import { fetchSettingsOptions } from "../api/settings";
import { bulkAssignCustomerManager, bulkUpdateCustomers, createCustomer, deleteCustomer, fetchCustomers, resetCustomerTraffic, type CustomerPayload } from "../api/customers";
import { useAuth } from "../api/auth";
import ExpiryModeField from "../components/ExpiryModeField";
import SubscriptionLinksModal from "../components/SubscriptionLinksModal";
import { buildExpiryPayload, DEFAULT_EXPIRY_MODE, formatDateValue, parseDateValue, type ExpiryMode } from "../utils/expiry";
import { extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess, notifyDataLoaded } from "../utils/feedback";

const { useBreakpoint } = Grid;
const RENEW_PRICE_PERIOD_OPTIONS = [
  { label: "月", value: "月" },
  { label: "季", value: "季" },
  { label: "年", value: "年" },
];
const CUSTOMER_PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
const CUSTOMER_PAGE_SIZE_STORAGE_KEY = "subsentry:customers-page-size";
const CUSTOMER_NOTES_MAX_LENGTH = 100;
const WEBHOOK_URL_RULES = [
  {
    validator: (_: unknown, value?: string) => {
      const cleanValue = String(value || "").trim();
      if (!cleanValue || cleanValue.startsWith("http://") || cleanValue.startsWith("https://")) {
        return Promise.resolve();
      }
      return Promise.reject(new Error("Webhook 地址必须以 http:// 或 https:// 开头"));
    },
  },
];

function getInitialCustomerPageSize() {
  if (typeof window === "undefined") {
    return 10;
  }
  const stored = Number(window.localStorage.getItem(CUSTOMER_PAGE_SIZE_STORAGE_KEY));
  return CUSTOMER_PAGE_SIZE_OPTIONS.includes(stored) ? stored : 10;
}

function UnitNumberInput({ value, onChange, unit, placeholder }: { value?: number; onChange?: (value: number | null) => void; unit: string; placeholder?: string }) {
  return (
    <div className="joined-unit-input">
      <InputNumber min={0} value={value} onChange={onChange} placeholder={placeholder} />
      <span className="joined-unit-label">{unit}</span>
    </div>
  );
}

type CustomerRow = {
  id: string;
  name: string;
  node: string;
  node_id: number;
  remote_email: string;
  manager: string;
  renew_price?: string;
  notes?: string;
  remaining_days: number;
  status_text: string;
  status_level: "expired" | "today" | "warning" | "healthy" | "disabled" | "unlimited";
  enable?: boolean;
  expiry_display?: string;
  is_unlimited_expiry?: boolean;
  inbound_ids?: number[];
  total_gb?: number;
  traffic_multiplier?: number;
};

type CustomerFormValues = {
  name: string;
  manager?: string;
  node_id: number;
  renew_price?: string;
  renew_price_amount?: string;
  renew_price_period?: "月" | "季" | "年";
  webhook_url?: string;
  notes?: string;
  inbound_ids?: number[];
  total_gb?: number;
  traffic_multiplier?: number;
  limit_ip?: number;
};

type BulkFormValues = {
  manager?: string;
  enable?: boolean;
  total_gb?: number;
  traffic_multiplier?: number;
  limit_ip?: number;
  renew_price_amount?: string;
  renew_price_period?: "月" | "季" | "年";
};

export default function CustomersPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<CustomerRow[]>([]);
  const [keyword, setKeyword] = useState("");
  const [nodeId, setNodeId] = useState<number | undefined>(undefined);
  const [manager, setManager] = useState("");
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [nodeOptions, setNodeOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [managerOptions, setManagerOptions] = useState<Array<{ label: string; value: string }>>([]);
  const [nodeInboundMap, setNodeInboundMap] = useState<Record<number, Array<{ label: string; value: number }>>>({});
  const [currentInboundOptions, setCurrentInboundOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [subscriptionOpen, setSubscriptionOpen] = useState(false);
  const [activeSubscriptionCustomerId, setActiveSubscriptionCustomerId] = useState("");
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<CustomerRow | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [resetTarget, setResetTarget] = useState<CustomerRow | null>(null);
  const [resetSubmitting, setResetSubmitting] = useState(false);
  const [bulkMode, setBulkMode] = useState<"manager" | "enable" | "traffic" | "expiry" | "renew_price">("manager");
  const [pageSize, setPageSize] = useState(getInitialCustomerPageSize);
  const [currentPage, setCurrentPage] = useState(1);
  const [expiryMode, setExpiryMode] = useState<ExpiryMode>(DEFAULT_EXPIRY_MODE);
  const [durationDays, setDurationDays] = useState<number | null>(30);
  const [customExpiryDate, setCustomExpiryDate] = useState<Dayjs | null>(null);
  const [bulkExpiryMode, setBulkExpiryMode] = useState<ExpiryMode>(DEFAULT_EXPIRY_MODE);
  const [bulkDurationDays, setBulkDurationDays] = useState<number | null>(30);
  const [bulkCustomExpiryDate, setBulkCustomExpiryDate] = useState<Dayjs | null>(null);
  const [form] = Form.useForm<CustomerFormValues>();
  const [bulkForm] = Form.useForm<BulkFormValues>();
  const notesValue = Form.useWatch("notes", form) || "";

  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const isAdmin = user?.role === "admin";
  const navigate = useNavigate();
  const deferredKeyword = useDeferredValue(keyword);
  const managerFilterOptions = useMemo(() => {
    if (!isAdmin) {
      const selfDisplayName = (user?.nickname || user?.username || "").trim();
      return selfDisplayName ? [{ label: selfDisplayName, value: selfDisplayName }] : [];
    }
    const optionMap = new Map<string, { label: string; value: string }>();
    for (const option of managerOptions) {
      optionMap.set(option.value, option);
    }
    for (const item of data) {
      const value = (item.manager || "").trim();
      if (value && !optionMap.has(value)) {
        optionMap.set(value, { label: value, value });
      }
    }
    return Array.from(optionMap.values());
  }, [data, isAdmin, managerOptions, user?.nickname, user?.username]);

  const filteredData = useMemo(() => {
    const cleanKeyword = deferredKeyword.trim().toLowerCase();
    const cleanManager = manager.trim();
    return data.filter((item) => {
      if (cleanKeyword) {
        const searchText = [item.name, item.node, item.manager, item.remote_email, item.renew_price, item.status_text]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!searchText.includes(cleanKeyword)) {
          return false;
        }
      }
      if (nodeId !== undefined && item.node_id !== nodeId) {
        return false;
      }
      if (isAdmin && cleanManager && (item.manager || "").trim() !== cleanManager) {
        return false;
      }
      return true;
    });
  }, [data, deferredKeyword, isAdmin, manager, nodeId]);

  const loadOptions = async (showSuccess = false) => {
    setOptionsLoading(true);
    try {
      const opts = await fetchSettingsOptions();
      setNodeOptions(opts.nodes.map((n) => ({ label: n.display_name || n.name, value: n.id })));
      setManagerOptions(opts.managers.map((m) => ({ label: m.name, value: m.name })));
      const inboundMap: Record<number, Array<{ label: string; value: number }>> = {};
      for (const item of opts.nodes) {
        const inbounds = ((item as any).inbounds || []).map((inbound: any) => ({
          label: `${inbound.remark} · ${String(inbound.protocol || "").toUpperCase()} · ${inbound.port}`,
          value: inbound.id,
        }));
        inboundMap[item.id] = inbounds;
      }
      setNodeInboundMap(inboundMap);
      if (showSuccess) {
        notifyDataLoaded("customers-options", "节点与经理选项已刷新");
      }
    } catch (error: any) {
      notifyActionError("customers-options", extractErrorMessage(error, "加载下拉选项失败"));
    } finally {
      setOptionsLoading(false);
    }
  };

  const loadData = async (showSuccess = false) => {
    setLoading(true);
    try {
      const res = await fetchCustomers();
      setData(Array.isArray(res.data) ? res.data : []);
      if (showSuccess) {
        notifyDataLoaded("customers-load", `客户列表已刷新，共 ${Array.isArray(res.data) ? res.data.length : 0} 条`);
      }
    } catch (error: any) {
      notifyActionError("customers-load", extractErrorMessage(error, "加载客户列表失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOptions();
  }, []);

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    if (!isAdmin) {
      setManager((user?.nickname || user?.username || "").trim());
    }
  }, [isAdmin, user?.nickname, user?.username]);

  useEffect(() => {
    setSelectedRowKeys([]);
  }, [deferredKeyword, nodeId, manager]);

  useEffect(() => {
    setCurrentPage(1);
  }, [deferredKeyword, nodeId, manager, pageSize]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(CUSTOMER_PAGE_SIZE_STORAGE_KEY, String(pageSize));
    }
  }, [pageSize]);

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(filteredData.length / pageSize));
    if (currentPage > maxPage) {
      setCurrentPage(maxPage);
    }
  }, [currentPage, filteredData.length, pageSize]);

  const expiryPreviewText = useMemo(() => {
    if (expiryMode === "date") {
      return formatDateValue(customExpiryDate) || "未选择";
    }
    return durationDays === null || durationDays === undefined ? "未计算" : `${durationDays} 天`;
  }, [customExpiryDate, durationDays, expiryMode]);

  const resetCreateState = () => {
    form.resetFields();
    form.setFieldsValue({
      manager: isAdmin ? "未分配" : user?.nickname || user?.username || "",
      renew_price_period: "月",
      total_gb: 0,
      traffic_multiplier: 5,
      limit_ip: 1,
    });
    setCurrentInboundOptions([]);
    setExpiryMode(DEFAULT_EXPIRY_MODE);
    setDurationDays(30);
    setCustomExpiryDate(null);
  };

  const openSubscription = (customerId: string) => {
    setActiveSubscriptionCustomerId(customerId);
    setSubscriptionOpen(true);
  };

  const openBulkModal = (mode: "manager" | "enable" | "traffic" | "expiry" | "renew_price") => {
    if (!selectedRowKeys.length) {
      notifyActionError("customer-bulk-empty", "请先选择客户");
      return;
    }
    setBulkMode(mode);
    bulkForm.resetFields();
    bulkForm.setFieldsValue({ enable: true, renew_price_period: "月" });
    setBulkExpiryMode(DEFAULT_EXPIRY_MODE);
    setBulkDurationDays(30);
    setBulkCustomExpiryDate(null);
    setBulkOpen(true);
  };

  const handleDelete = async (id: string) => {
    try {
      notifyActionLoading("customer-delete", "删除客户中...");
      await deleteCustomer(id);
      notifyActionSuccess("customer-delete", "删除客户成功");
      await loadData(false);
    } catch (error: any) {
      notifyActionError("customer-delete", extractErrorMessage(error, "删除客户失败"));
    }
  };

  const handleResetTraffic = async (row: CustomerRow) => {
    setResetSubmitting(true);
    try {
      notifyActionLoading("customer-reset-traffic", "重置客户流量中...");
      const result = await resetCustomerTraffic(row.id);
      notifyActionSuccess("customer-reset-traffic", result.message || "客户流量已重置");
      setResetTarget(null);
      await loadData(false);
    } catch (error: any) {
      notifyActionError("customer-reset-traffic", extractErrorMessage(error, "重置客户流量失败"));
    } finally {
      setResetSubmitting(false);
    }
  };

  const openResetTrafficConfirm = (row: CustomerRow) => {
    setResetTarget(row);
  };

  const submitCreate = async () => {
    const values = await form.validateFields();
    const renewPriceAmount = String(values.renew_price_amount || "").trim();
    const renewPrice = renewPriceAmount ? `${renewPriceAmount}/${values.renew_price_period || "月"}` : "未设置";
    const payload: CustomerPayload = {
      name: values.name,
      manager: isAdmin ? (values.manager || "未分配") : undefined,
      node: "",
      node_id: values.node_id,
      renew_price: renewPrice,
      webhook_url: values.webhook_url,
      notes: values.notes,
      inbound_ids: values.inbound_ids,
      total_gb: values.total_gb,
      traffic_multiplier: values.traffic_multiplier,
      limit_ip: values.limit_ip ?? 1,
      ...buildExpiryPayload(expiryMode, durationDays, customExpiryDate),
    };
    try {
      setCreateSubmitting(true);
      notifyActionLoading("customer-create", "添加客户中...");
      const result = await createCustomer(payload);
      notifyActionSuccess("customer-create", result.message || "添加客户成功");
      setCreateOpen(false);
      resetCreateState();
      await loadData(false);
      if (result.customer_id) {
        openSubscription(result.customer_id);
      } else {
        const latest = await fetchCustomers({ keyword: values.name });
        const created = latest.data?.find((item) => item.name === values.name) || latest.data?.[0];
        if (created?.id) {
          openSubscription(created.id);
        }
      }
    } catch (error: any) {
      notifyActionError("customer-create", extractErrorMessage(error, "创建客户失败"));
    } finally {
      setCreateSubmitting(false);
    }
  };

  const submitBulk = async () => {
    const values = await bulkForm.validateFields();
    const customerIds = selectedRowKeys.map(String);
    const bulkRenewPriceAmount = String(values.renew_price_amount || "").trim();
    const bulkRenewPrice = bulkRenewPriceAmount ? `${bulkRenewPriceAmount}/${values.renew_price_period || "月"}` : "";
    const trafficPayload = {
      ...(values.total_gb !== undefined && values.total_gb !== null ? { total_gb: values.total_gb } : {}),
      ...(values.traffic_multiplier !== undefined && values.traffic_multiplier !== null ? { traffic_multiplier: values.traffic_multiplier } : {}),
      ...(values.limit_ip !== undefined && values.limit_ip !== null ? { limit_ip: values.limit_ip } : {}),
    };
    if (bulkMode === "traffic" && Object.keys(trafficPayload).length === 0) {
      notifyActionError("customer-bulk", "请至少填写一个要批量修改的流量字段");
      return;
    }
    try {
      setBulkSubmitting(true);
      notifyActionLoading("customer-bulk", "批量操作中...");
      const result =
        bulkMode === "manager"
          ? await bulkAssignCustomerManager(customerIds, values.manager || "未分配")
          : await bulkUpdateCustomers({
              customer_ids: customerIds,
              ...(bulkMode === "enable" ? { enable: values.enable } : {}),
              ...(bulkMode === "traffic" ? trafficPayload : {}),
              ...(bulkMode === "expiry" ? buildExpiryPayload(bulkExpiryMode, bulkDurationDays, bulkCustomExpiryDate) : {}),
              ...(bulkMode === "renew_price" ? { renew_price: bulkRenewPrice } : {}),
            });
      if (result.errors?.length) {
        notifyActionError("customer-bulk", result.message || "部分客户处理失败");
      } else {
        notifyActionSuccess("customer-bulk", result.message || "批量操作完成");
      }
      setBulkOpen(false);
      setSelectedRowKeys([]);
      await loadData(false);
    } catch (error: any) {
      notifyActionError("customer-bulk", extractErrorMessage(error, "批量操作失败"));
    } finally {
      setBulkSubmitting(false);
    }
  };

  const renderBadge = (row: CustomerRow) => {
    switch (row.status_level) {
      case "disabled":
        return <span className="apple-badge custom-muted">已停用</span>;
      case "unlimited":
        return <span className="apple-badge custom-info">无限期</span>;
      case "expired":
        return <span className="apple-badge custom-danger">{row.status_text || "已过期"}</span>;
      case "today":
        return <span className="apple-badge custom-warning">{row.status_text || "今天到期"}</span>;
      case "warning":
        return <span className="apple-badge custom-warning">{row.status_text}</span>;
      default:
        return <span className="apple-badge custom-success">{row.status_text || "正常"}</span>;
    }
  };

  const renderMobileStatus = (row: CustomerRow) => {
    switch (row.status_level) {
      case "disabled":
        return <div className="sub-status-card status-muted"><span className="status-val">已停用</span><span className="status-lbl">暂停</span></div>;
      case "unlimited":
        return <div className="sub-status-card status-info"><span className="status-val">无限期</span><span className="status-lbl">长期</span></div>;
      case "expired":
        return <div className="sub-status-card status-danger"><span className="status-val">已过期</span><span className="status-lbl">{Math.abs(row.remaining_days)} 天</span></div>;
      case "today":
        return <div className="sub-status-card status-warning"><span className="status-val">今天到期</span><span className="status-lbl">请处理</span></div>;
      case "warning":
        return <div className="sub-status-card status-warning"><span className="status-val">将到期</span><span className="status-lbl">{row.status_text.replace("剩余 ", "")}</span></div>;
      default:
        return <div className="sub-status-card status-success"><span className="status-val">服务中</span><span className="status-lbl">{row.status_text.replace("剩余 ", "")}</span></div>;
    }
  };

  const bulkMenuItems: MenuProps["items"] = [
    ...(isAdmin ? [{ key: "manager", label: "分配客户经理" }] : []),
    { key: "expiry", label: "调整到期时间" },
    { key: "renew_price", label: "设置续费价格" },
    { key: "traffic", label: "调整流量/IP" },
    { key: "enable", label: "启用或停用" },
  ];

  const openDeleteConfirm = (row: CustomerRow) => {
    setDeleteTarget(row);
  };

  const confirmDeleteTarget = async () => {
    if (!deleteTarget) {
      return;
    }
    setDeleteSubmitting(true);
    try {
      await handleDelete(deleteTarget.id);
      setDeleteTarget(null);
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const columns: ColumnsType<CustomerRow> = [
    { title: "客户名称", dataIndex: "name", key: "name", render: (text, row) => <Link to={`/customers/${row.id}`} style={{ fontWeight: 600, color: "var(--apple-blue)" }}>{text}</Link> },
    { title: "节点", dataIndex: "node", key: "node", ellipsis: true },
    { title: "客户经理", dataIndex: "manager", key: "manager" },
    { title: "续费价格", dataIndex: "renew_price", key: "renew_price", width: 120, render: (value) => value || "未设置" },
    { title: "状态", key: "remaining_days", width: 140, render: (_, row) => renderBadge(row) },
    {
      title: "操作",
      key: "action",
      align: "right",
      width: 190,
      render: (_, row) => (
        <Space size={4}>
          <Button type="text" icon={<LinkOutlined />} onClick={() => openSubscription(row.id)} />
          <Popconfirm title="确认重置该客户流量？" description="仅清空已用上传/下载流量，不改变总流量、到期时间、倍率和 IP 限制。" onConfirm={() => handleResetTraffic(row)} okText="确认重置" cancelText="取消">
            <Button type="text" icon={<SyncOutlined />} />
          </Popconfirm>
          <Popconfirm title="确定要删除该客户吗？" description="此操作不可逆，将同步抹除历史日志。" onConfirm={() => handleDelete(row.id)} okText="确定" cancelText="取消" okButtonProps={{ danger: true }}>
            <Button type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
          <Button type="text" icon={<ArrowRightOutlined />} onClick={() => navigate(`/customers/${row.id}`)} />
        </Space>
      ),
    },
  ];

  return (
    <div>
      <style>{`
        .apple-filter-box { background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: 14px; padding: ${isMobile ? "10px" : "14px"}; margin-bottom: 12px; }
        .apple-badge { font-size: 11px; font-weight: 600; padding: 4px 8px; border-radius: 6px; display: inline-block; }
        .apple-badge.custom-danger { background: var(--status-danger-bg); color: var(--status-danger); border: 1px solid var(--status-danger-border); }
        .apple-badge.custom-warning { background: var(--status-warning-bg); color: var(--status-warning); border: 1px solid var(--status-warning-border); }
        .apple-badge.custom-success { background: var(--status-success-bg); color: var(--status-success); border: 1px solid var(--status-success-border); }
        .apple-badge.custom-info { background: var(--status-info-bg); color: var(--status-info); border: 1px solid var(--status-info-border); }
        .apple-badge.custom-muted { background: var(--status-muted-bg); color: var(--status-muted); border: 1px solid var(--status-muted-border); }
        .apple-subscription-card { background: var(--glass-bg); border-radius: 14px; padding: 10px 10px 10px 14px; margin-bottom: 9px; display: flex; justify-content: space-between; align-items: center; border: 1px solid var(--glass-border); box-shadow: var(--shadow-smooth); transition: all 0.2s ease; position: relative; overflow: hidden; gap: 9px; }
        .apple-subscription-card:active { transform: scale(0.99); background: color-mix(in srgb, var(--glass-bg) 88%, var(--apple-blue) 12%); }
        .card-decorator { position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: #e5e5ea; }
        .apple-subscription-card.has-danger .card-decorator { background: var(--status-danger); }
        .apple-subscription-card.has-warning .card-decorator { background: var(--status-warning); }
        .apple-subscription-card.has-success .card-decorator { background: var(--status-success); }
        .apple-subscription-card.has-info .card-decorator { background: var(--status-info); }
        .apple-subscription-card.has-muted .card-decorator { background: var(--status-muted); }
        .sub-main-info { display: flex; flex-direction: column; gap: 6px; flex: 1; min-width: 0; }
        .sub-title { font-size: 15px; font-weight: 650; color: var(--text-main); line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .sub-meta-row { display: flex; gap: 5px; flex-wrap: nowrap; overflow: hidden; width: 100%; }
        .sub-meta-pill { display: inline-flex; align-items: center; gap: 4px; background: var(--surface-soft); color: var(--text-sub); padding: 2px 7px; border-radius: 6px; font-size: 11px; font-weight: 500; white-space: nowrap; max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
        .sub-side-stack { display: flex; align-items: center; gap: 3px; flex-shrink: 0; }
        .sub-more-button { width: 26px; min-width: 26px; height: 30px; color: var(--text-sub); }
        .sub-status-card { display: flex; flex-direction: column; align-items: center; justify-content: center; width: 76px; height: 54px; border-radius: 12px; text-align: center; padding: 4px; }
        .sub-status-card .status-val { font-size: 11px; font-weight: 500; opacity: 0.85; margin-bottom: 1px; }
        .sub-status-card .status-lbl { font-size: 14px; font-weight: 700; }
        .status-danger { background: var(--status-danger-bg); color: var(--status-danger); }
        .status-warning { background: var(--status-warning-bg); color: var(--status-warning); }
        .status-success { background: var(--status-success-bg); color: var(--status-success); }
        .status-info { background: var(--status-info-bg); color: var(--status-info); }
        .status-muted { background: var(--status-muted-bg); color: var(--status-muted); }
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
        .customer-notes-textarea {
          resize: none !important;
          overflow: hidden !important;
        }
        .customer-notes-textarea::-webkit-scrollbar {
          width: 0;
          height: 0;
          display: none;
        }
        .customer-notes-count {
          margin-top: 6px;
          text-align: right;
          color: var(--text-sub);
          font-size: 12px;
          line-height: 1;
        }
      `}</style>

      <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", justifyContent: "space-between", alignItems: isMobile ? "stretch" : "center", marginBottom: 14, gap: 12 }}>
        <div>
          <Typography.Title level={isMobile ? 4 : 3} style={{ margin: 0, fontWeight: 700 }}>客户管理</Typography.Title>
          {!isMobile && <Typography.Paragraph type="secondary" style={{ margin: 0, fontSize: 13 }}>配置并监控所有签约主机的到期资产与通知策略。</Typography.Paragraph>}
        </div>
        <Space wrap size={8} style={{ justifyContent: isMobile ? "flex-start" : "flex-end", width: isMobile ? "100%" : "auto" }}>
          <Dropdown
            disabled={!selectedRowKeys.length}
            menu={{
              items: bulkMenuItems,
              onClick: ({ key }) => openBulkModal(key as "manager" | "enable" | "traffic" | "expiry" | "renew_price"),
            }}
          >
            <Button style={isMobile ? { flex: "1 1 140px" } : undefined} disabled={!selectedRowKeys.length}>
              批量操作{selectedRowKeys.length ? ` (${selectedRowKeys.length})` : ""}
            </Button>
          </Dropdown>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => void Promise.all([loadData(true), loadOptions(true)])}
            style={isMobile ? { width: 44, minWidth: 44, paddingInline: 0 } : undefined}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              resetCreateState();
              setCreateOpen(true);
            }}
            style={isMobile ? { flex: "1 1 140px", borderRadius: 8, background: "var(--apple-blue)" } : { borderRadius: 8, background: "var(--apple-blue)" }}
          >
            新增客户
          </Button>
        </Space>
      </div>

      <div className="apple-filter-box">
        <Row gutter={[10, 10]} align="middle">
          <Col xs={24} sm={10}>
            <Input prefix={<SearchOutlined style={{ color: "var(--text-sub)" }} />} placeholder="搜索客户名称关键字..." value={keyword} onChange={(e) => setKeyword(e.target.value)} onPressEnter={() => void loadData(true)} style={{ borderRadius: 8 }} allowClear />
          </Col>
          <Col xs={12} sm={7}>
            <Select
              placeholder="筛选所属集群节点"
              style={{ width: "100%" }}
              value={nodeId}
              onChange={(value) => setNodeId(value)}
              options={nodeOptions}
              loading={optionsLoading}
              allowClear
            />
          </Col>
          <Col xs={12} sm={7}>
            <Select
              placeholder="筛选客户经理"
              style={{ width: "100%" }}
              value={manager || undefined}
              onChange={(v) => setManager(v || "")}
              options={managerFilterOptions}
              allowClear={isAdmin}
            />
          </Col>
        </Row>
      </div>

      {isMobile ? (
        <>
          {selectedRowKeys.length ? (
            <Card bordered={false} style={{ borderRadius: 14, marginBottom: 10, background: "var(--surface-soft)" }} bodyStyle={{ padding: "8px 12px" }}>
              <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
                <Typography.Text style={{ color: "var(--apple-blue)", fontWeight: 600 }}>已选 {selectedRowKeys.length} 个客户</Typography.Text>
                <Button size="small" type="text" onClick={() => setSelectedRowKeys([])}>清空</Button>
              </Space>
            </Card>
          ) : null}
          <div style={{ marginBottom: 10 }}>
              <Checkbox
                checked={filteredData.length > 0 && selectedRowKeys.length === filteredData.length}
                indeterminate={selectedRowKeys.length > 0 && selectedRowKeys.length < filteredData.length}
                onChange={(event) => setSelectedRowKeys(event.target.checked ? filteredData.map((item) => item.id) : [])}
              >
                全选当前列表
              </Checkbox>
          </div>
          <List
            loading={loading}
            dataSource={filteredData}
            renderItem={(item) => {
              const statusClass = item.status_level === "expired" ? "has-danger" : item.status_level === "today" || item.status_level === "warning" ? "has-warning" : item.status_level === "unlimited" ? "has-info" : item.status_level === "disabled" ? "has-muted" : "has-success";
              const checked = selectedRowKeys.includes(item.id);
              return (
                <div className={`apple-subscription-card ${statusClass}`} onClick={() => navigate(`/customers/${item.id}`)}>
                  <div className="card-decorator" />
                  <Checkbox
                    checked={checked}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => {
                      setSelectedRowKeys((keys) => e.target.checked ? [...keys, item.id] : keys.filter((key) => key !== item.id));
                    }}
                  />
                  <div className="sub-main-info">
                    <div className="sub-title">{item.name}</div>
                    <div className="sub-meta-row">
                      <span className="sub-meta-pill"><ClusterOutlined style={{ fontSize: 10 }} />{item.node}</span>
                      <span className="sub-meta-pill"><UserOutlined style={{ fontSize: 10 }} />{item.manager}</span>
                      <span className="sub-meta-pill"><WalletOutlined style={{ fontSize: 10 }} />{item.renew_price || "未设置"}</span>
                    </div>
                  </div>
                  <div
                    className="sub-side-stack"
                    onClick={(event) => event.stopPropagation()}
                    onPointerDown={(event) => event.stopPropagation()}
                    onTouchStart={(event) => event.stopPropagation()}
                  >
                    {renderMobileStatus(item)}
                    <Dropdown
                      trigger={["click"]}
                      menu={{
                        items: [
                          { key: "subscription", label: "查看订阅链接", icon: <LinkOutlined /> },
                          { key: "reset-traffic", label: "重置流量", icon: <SyncOutlined /> },
                          { key: "detail", label: "进入详情", icon: <ArrowRightOutlined /> },
                          { key: "delete", label: "删除客户", danger: true, icon: <DeleteOutlined /> },
                        ],
                        onClick: ({ key, domEvent }) => {
                          domEvent.stopPropagation();
                          if (key === "subscription") {
                            openSubscription(item.id);
                          } else if (key === "reset-traffic") {
                            openResetTrafficConfirm(item);
                          } else if (key === "detail") {
                            navigate(`/customers/${item.id}`);
                          } else if (key === "delete") {
                            openDeleteConfirm(item);
                          }
                        },
                      }}
                    >
                      <Button
                        className="sub-more-button"
                        size="small"
                        type="text"
                        icon={<MoreOutlined />}
                        onClick={(e) => e.stopPropagation()}
                        onPointerDown={(e) => e.stopPropagation()}
                        onTouchStart={(e) => e.stopPropagation()}
                      />
                    </Dropdown>
                  </div>
                </div>
              );
            }}
          />
        </>
      ) : (
        <Card className="apple-fluid-card" bordered={false} bodyStyle={{ padding: "8px 16px" }}>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={filteredData}
            rowSelection={{ selectedRowKeys, onChange: (keys) => setSelectedRowKeys(keys.map(String)) }}
            pagination={{
              current: currentPage,
              pageSize,
              total: filteredData.length,
              size: "small",
              showSizeChanger: true,
              pageSizeOptions: CUSTOMER_PAGE_SIZE_OPTIONS.map(String),
              showTotal: (total) => `共 ${total} 个客户`,
              onChange: (page, nextPageSize) => {
                setCurrentPage(page);
                if (nextPageSize !== pageSize) {
                  setPageSize(nextPageSize);
                }
              },
            }}
            size="middle"
          />
        </Card>
      )}

      <Modal
        open={Boolean(deleteTarget)}
        title="确认删除该客户？"
        onCancel={() => setDeleteTarget(null)}
        onOk={() => void confirmDeleteTarget()}
        confirmLoading={deleteSubmitting}
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        width={isMobile ? "calc(100vw - 24px)" : undefined}
        destroyOnClose
      >
        <Typography.Text>
          客户 [ {deleteTarget?.name || "-"} ] 的全部订阅资产都将被抹除，且无法恢复。
        </Typography.Text>
      </Modal>

      <Modal
        open={Boolean(resetTarget)}
        title="确认重置该客户流量？"
        onCancel={() => setResetTarget(null)}
        onOk={() => resetTarget ? handleResetTraffic(resetTarget) : undefined}
        confirmLoading={resetSubmitting}
        okText="确认重置"
        cancelText="取消"
        width={isMobile ? "calc(100vw - 24px)" : undefined}
        destroyOnClose
      >
        <Typography.Text>
          客户 [ {resetTarget?.name || "-"} ] 的已用上传/下载流量会清零，不会改变总流量、到期时间、倍率和 IP 限制。
        </Typography.Text>
      </Modal>

      <Modal
        open={createOpen}
        title="新增客户"
        onCancel={() => setCreateOpen(false)}
        onOk={submitCreate}
        confirmLoading={createSubmitting}
        okText="创建"
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
        <Form form={form} layout="vertical" className="customer-editor-form">
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item name="name" label="客户名称" rules={[{ required: true, message: "请输入客户名称" }]}>
                <Input placeholder="系统会自动生成 3X-UI 邮箱标识" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              {isAdmin ? (
                <Form.Item name="manager" label="客户经理">
                  <Select allowClear options={managerOptions} />
                </Form.Item>
              ) : (
                <Form.Item label="客户经理">
                  <Input value={user?.nickname || user?.username || ""} disabled />
                </Form.Item>
              )}
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="node_id" label="节点" rules={[{ required: true, message: "请选择节点" }]}>
                <Select
                  allowClear
                  loading={optionsLoading}
                  options={nodeOptions}
                  onChange={(value) => {
                    const options = nodeInboundMap[Number(value)] || [];
                    setCurrentInboundOptions(options);
                    form.setFieldValue("inbound_ids", []);
                  }}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="inbound_ids" label="挂载入站" rules={[{ required: true, message: "请选择至少一个入站" }]}>
                <Select mode="multiple" options={currentInboundOptions} maxTagCount="responsive" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item label="到期设置">
                <ExpiryModeField
                  mode={expiryMode}
                  onModeChange={setExpiryMode}
                  durationDays={durationDays}
                  onDurationDaysChange={(value) => setDurationDays(value ?? null)}
                  targetDate={customExpiryDate}
                  onTargetDateChange={setCustomExpiryDate}
                  previewLabel="预计到期日"
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
                    <UnitNumberInput unit="IP" placeholder="默认 1，0 表示不限制 IP" />
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
              <Form.Item name="webhook_url" label="Webhook 地址" rules={WEBHOOK_URL_RULES}>
                <Input placeholder="可留空，使用全局默认 Webhook" />
              </Form.Item>
            </Col>
            <Col xs={24}>
              <Form.Item name="notes" label="备注" style={{ marginBottom: 0 }}>
                <Input.TextArea rows={2} maxLength={CUSTOMER_NOTES_MAX_LENGTH} placeholder="填写客户备注，仅保存在 SubSentry 本地" className="customer-notes-textarea" />
              </Form.Item>
              <div className="customer-notes-count">{String(notesValue).length} / {CUSTOMER_NOTES_MAX_LENGTH}</div>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        open={bulkOpen}
        title={{
          manager: "批量分配客户经理",
          enable: "批量启停客户",
          traffic: "批量调整流量",
          expiry: "批量调整到期时间",
          renew_price: "批量设置续费价格",
        }[bulkMode]}
        onCancel={() => setBulkOpen(false)}
        onOk={submitBulk}
        confirmLoading={bulkSubmitting}
        okText="执行"
        destroyOnClose
        width={isMobile ? "calc(100vw - 24px)" : undefined}
      >
        <Typography.Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
          已选择 {selectedRowKeys.length} 个客户。
        </Typography.Text>
        <Form form={bulkForm} layout="vertical">
          {bulkMode === "manager" ? (
            <Form.Item name="manager" label="客户经理" rules={[{ required: true, message: "请选择客户经理" }]}>
              <Select options={managerOptions} />
            </Form.Item>
          ) : null}
          {bulkMode === "enable" ? (
            <Form.Item name="enable" label="启用状态" rules={[{ required: true, message: "请选择启用状态" }]}>
              <Select options={[{ label: "启用", value: true }, { label: "停用", value: false }]} />
            </Form.Item>
          ) : null}
          {bulkMode === "traffic" ? (
            <>
              <Typography.Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
                留空表示不修改该字段；总流量和 IP 限制填 0 表示改为不限制。
              </Typography.Text>
              <Form.Item name="total_gb" label="总流量上限 (GB)">
                <InputNumber min={0} style={{ width: "100%" }} placeholder="0 表示不限流量" />
              </Form.Item>
              <Form.Item name="traffic_multiplier" label="流量扣减倍率">
                <InputNumber min={1} max={100} step={0.1} style={{ width: "100%" }} placeholder="5 表示按 5 倍扣减" />
              </Form.Item>
              <Form.Item name="limit_ip" label="IP 限制">
                <InputNumber min={0} style={{ width: "100%" }} placeholder="0 表示不限制" />
              </Form.Item>
            </>
          ) : null}
          {bulkMode === "renew_price" ? (
            <Form.Item label="续费价格" required>
              <div className="joined-price-input">
                <Form.Item name="renew_price_amount" noStyle rules={[{ required: true, message: "请输入续费价格" }]}>
                  <Input placeholder="例如：40" />
                </Form.Item>
                <Form.Item name="renew_price_period" noStyle>
                  <Select options={RENEW_PRICE_PERIOD_OPTIONS} />
                </Form.Item>
              </div>
            </Form.Item>
          ) : null}
          {bulkMode === "expiry" ? (
            <Form.Item label="到期设置">
              <ExpiryModeField
                mode={bulkExpiryMode}
                onModeChange={setBulkExpiryMode}
                durationDays={bulkDurationDays}
                onDurationDaysChange={(value) => setBulkDurationDays(value ?? null)}
                targetDate={bulkCustomExpiryDate}
                onTargetDateChange={setBulkCustomExpiryDate}
                previewLabel="批量保存后到期日"
                baseDateText="今天"
              />
            </Form.Item>
          ) : null}
        </Form>
      </Modal>

      <SubscriptionLinksModal
        customerId={activeSubscriptionCustomerId}
        open={subscriptionOpen}
        onClose={() => setSubscriptionOpen(false)}
      />
    </div>
  );
}
