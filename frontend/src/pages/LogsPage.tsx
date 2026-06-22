import { useEffect, useState } from "react";
import { Button, Card, Drawer, Grid, Input, List, Select, Space, Table, Tabs, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined, SearchOutlined, SyncOutlined } from "@ant-design/icons";
import {
  fetchActivityCategories,
  fetchActivityLogs,
  fetchNotificationLogs,
  retryNotificationLog,
  type ActivityLogRow,
  type NotificationLogRow,
} from "../api/logs";
import { extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess, notifyDataLoaded } from "../utils/feedback";
import { formatJsonForDisplay } from "../utils/display";

const { useBreakpoint } = Grid;

const ACTIVITY_CATEGORY_OPTIONS = [
  { label: "全部类型", value: "" },
  { label: "登录", value: "auth" },
  { label: "节点", value: "node" },
  { label: "批量操作", value: "bulk" },
  { label: "客户", value: "customer" },
  { label: "用户", value: "user" },
  { label: "财务", value: "finance" },
  { label: "通知", value: "notification" },
];

const STATUS_OPTIONS = [
  { label: "全部状态", value: "" },
  { label: "成功", value: "success" },
  { label: "失败", value: "failed" },
  { label: "等待中", value: "pending" },
];

const EVENT_OPTIONS = [
  { label: "全部事件", value: "" },
  { label: "到期提醒", value: "expiry_warning" },
  { label: "流量不足", value: "traffic_low" },
  { label: "客户停用", value: "customer_disabled" },
  { label: "节点异常", value: "node_abnormal" },
  { label: "经理汇总", value: "manager_summary" },
  { label: "测试发送", value: "test" },
];

const ACTIVITY_CATEGORY_LABELS: Record<string, string> = {
  auth: "登录",
  node: "节点",
  bulk: "批量操作",
  customer: "客户",
  user: "用户",
  finance: "财务",
  notification: "通知",
};

function statusTag(status: string) {
  const color = status === "success" ? "green" : status === "failed" ? "red" : "blue";
  const text = status === "success" ? "成功" : status === "failed" ? "失败" : "等待中";
  return <Tag color={color}>{text}</Tag>;
}

function eventLabel(value: string) {
  return EVENT_OPTIONS.find((item) => item.value === value)?.label || value || "-";
}

export default function LogsPage() {
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const isCompactDesktop = !isMobile && screens.xl === false;
  const useCardList = isMobile || isCompactDesktop;
  const [activityRows, setActivityRows] = useState<ActivityLogRow[]>([]);
  const [notificationRows, setNotificationRows] = useState<NotificationLogRow[]>([]);
  const [activityLoading, setActivityLoading] = useState(false);
  const [notificationLoading, setNotificationLoading] = useState(false);
  const [activityPage, setActivityPage] = useState(1);
  const [activityPageSize, setActivityPageSize] = useState(20);
  const [activityTotal, setActivityTotal] = useState(0);
  const [notificationPage, setNotificationPage] = useState(1);
  const [notificationPageSize, setNotificationPageSize] = useState(20);
  const [notificationTotal, setNotificationTotal] = useState(0);
  const [category, setCategory] = useState("");
  const [activityCategoryOptions, setActivityCategoryOptions] = useState(ACTIVITY_CATEGORY_OPTIONS);
  const [keyword, setKeyword] = useState("");
  const [notifyStatus, setNotifyStatus] = useState("");
  const [eventType, setEventType] = useState("");
  const [detailOpen, setDetailOpen] = useState(false);
  const [activeDetail, setActiveDetail] = useState<{ title: string; content: string } | null>(null);

  const loadActivity = async (page = activityPage, perPage = activityPageSize, showSuccess = false) => {
    setActivityLoading(true);
    try {
      const data = await fetchActivityLogs({ page, per_page: perPage, category, keyword });
      setActivityRows(data.items || []);
      setActivityTotal(data.total || 0);
      setActivityPage(data.page || page);
      setActivityPageSize(data.per_page || perPage);
      if (showSuccess) {
        notifyDataLoaded("activity-logs-load", `操作日志已刷新，共 ${data.total || 0} 条`);
      }
    } catch (error: any) {
      notifyActionError("activity-logs-load", extractErrorMessage(error, "加载操作日志失败"));
    } finally {
      setActivityLoading(false);
    }
  };

  const loadActivityCategories = async () => {
    try {
      const categories = await fetchActivityCategories();
      const optionMap = new Map(ACTIVITY_CATEGORY_OPTIONS.map((item) => [item.value, item]));
      for (const item of categories || []) {
        if (!optionMap.has(item)) {
          optionMap.set(item, { label: ACTIVITY_CATEGORY_LABELS[item] || item, value: item });
        }
      }
      setActivityCategoryOptions(Array.from(optionMap.values()));
    } catch {
      setActivityCategoryOptions(ACTIVITY_CATEGORY_OPTIONS);
    }
  };

  const loadNotifications = async (page = notificationPage, perPage = notificationPageSize, showSuccess = false) => {
    setNotificationLoading(true);
    try {
      const data = await fetchNotificationLogs({ page, per_page: perPage, status: notifyStatus, event_type: eventType });
      setNotificationRows(data.items || []);
      setNotificationTotal(data.total || 0);
      setNotificationPage(data.page || page);
      setNotificationPageSize(data.per_page || perPage);
      if (showSuccess) {
        notifyDataLoaded("notification-logs-load", `通知日志已刷新，共 ${data.total || 0} 条`);
      }
    } catch (error: any) {
      notifyActionError("notification-logs-load", extractErrorMessage(error, "加载通知日志失败"));
    } finally {
      setNotificationLoading(false);
    }
  };

  useEffect(() => {
    void loadActivityCategories();
    void loadActivity(1, activityPageSize, false);
  }, [category]);

  useEffect(() => {
    void loadNotifications(1, notificationPageSize, false);
  }, [notifyStatus, eventType]);

  const openDetail = (title: string, content?: string) => {
    setActiveDetail({ title, content: formatJsonForDisplay(content) });
    setDetailOpen(true);
  };

  const retryLog = async (row: NotificationLogRow) => {
    try {
      notifyActionLoading("notification-retry", `重试通知 #${row.id} 中...`);
      const result = await retryNotificationLog(row.id);
      notifyActionSuccess("notification-retry", result.message || "通知已重试");
      await loadNotifications(notificationPage, notificationPageSize, false);
    } catch (error: any) {
      notifyActionError("notification-retry", extractErrorMessage(error, "通知重试失败"));
    }
  };

  const activityColumns: ColumnsType<ActivityLogRow> = [
    { title: "时间", dataIndex: "created_at", key: "created_at", width: 170 },
    { title: "类型", dataIndex: "category", key: "category", width: 110, render: (value) => <Tag>{value}</Tag> },
    { title: "动作", dataIndex: "action", key: "action", width: 140 },
    { title: "操作人", dataIndex: "actor", key: "actor", width: 130, render: (value) => value || "-" },
    { title: "目标", key: "target", width: 190, render: (_, row) => row.target_name || row.target_id || "-" },
    { title: "状态", dataIndex: "status", key: "status", width: 90, render: statusTag },
    { title: "摘要", dataIndex: "summary", key: "summary", ellipsis: true },
    {
      title: "详情",
      key: "detail",
      width: 90,
      align: "right",
      render: (_, row) => <Button size="small" onClick={() => openDetail(`操作日志 #${row.id}`, row.detail)}>查看</Button>,
    },
  ];

  const notificationColumns: ColumnsType<NotificationLogRow> = [
    { title: "时间", dataIndex: "created_at", key: "created_at", width: 170 },
    { title: "事件", dataIndex: "event_type", key: "event_type", width: 120, render: (value) => <Tag color="processing">{eventLabel(value)}</Tag> },
    { title: "模式", dataIndex: "send_mode", key: "send_mode", width: 120 },
    { title: "客户", dataIndex: "customer_name", key: "customer_name", width: 160, render: (value) => value || "-" },
    { title: "客户经理", dataIndex: "manager", key: "manager", width: 130, render: (value) => value || "-" },
    { title: "状态", dataIndex: "status", key: "status", width: 90, render: statusTag },
    { title: "响应", dataIndex: "response_status", key: "response_status", width: 90, render: (value) => value || "-" },
    { title: "重试", dataIndex: "retry_count", key: "retry_count", width: 80 },
    { title: "错误", dataIndex: "error_message", key: "error_message", ellipsis: true, render: (value) => value || "-" },
    {
      title: "操作",
      key: "action",
      width: 150,
      align: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" onClick={() => openDetail(`通知日志 #${row.id}`, [row.error_message, row.response_text].filter(Boolean).join("\n\n"))}>详情</Button>
          <Button size="small" icon={<SyncOutlined />} disabled={row.status !== "failed"} onClick={() => void retryLog(row)}>重试</Button>
        </Space>
      ),
    },
  ];

  const renderActivityList = () => (
    <List
      loading={activityLoading}
      dataSource={activityRows}
      renderItem={(row) => (
        <Card bordered={false} style={{ borderRadius: 16, marginBottom: 12 }} bodyStyle={{ padding: 14 }}>
          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            <Space wrap>
              <Tag>{row.category}</Tag>
              {statusTag(row.status)}
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>{row.created_at}</Typography.Text>
            </Space>
            <Typography.Text strong>{row.summary}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>操作人：{row.actor || "-"} / 目标：{row.target_name || row.target_id || "-"}</Typography.Text>
            <Button size="small" onClick={() => openDetail(`操作日志 #${row.id}`, row.detail)}>查看详情</Button>
          </Space>
        </Card>
      )}
      pagination={{ current: activityPage, pageSize: activityPageSize, total: activityTotal, size: "small", onChange: (page, perPage) => void loadActivity(page, perPage, true) }}
    />
  );

  const renderNotificationList = () => (
    <List
      loading={notificationLoading}
      dataSource={notificationRows}
      renderItem={(row) => (
        <Card bordered={false} style={{ borderRadius: 16, marginBottom: 12 }} bodyStyle={{ padding: 14 }}>
          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            <Space wrap>
              <Tag color="processing">{eventLabel(row.event_type)}</Tag>
              {statusTag(row.status)}
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>{row.created_at}</Typography.Text>
            </Space>
            <Typography.Text strong>{row.customer_name || row.manager || row.send_mode}</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>模式：{row.send_mode} / 响应：{row.response_status || "-"}</Typography.Text>
            {row.error_message ? <Typography.Text type="danger" style={{ fontSize: 12 }}>{row.error_message}</Typography.Text> : null}
            <Space wrap>
              <Button size="small" onClick={() => openDetail(`通知日志 #${row.id}`, [row.error_message, row.response_text].filter(Boolean).join("\n\n"))}>详情</Button>
              <Button size="small" icon={<SyncOutlined />} disabled={row.status !== "failed"} onClick={() => void retryLog(row)}>重试</Button>
            </Space>
          </Space>
        </Card>
      )}
      pagination={{ current: notificationPage, pageSize: notificationPageSize, total: notificationTotal, size: "small", onChange: (page, perPage) => void loadNotifications(page, perPage, true) }}
    />
  );

  return (
    <div style={{ minWidth: 0, overflowX: "hidden" }}>
      <div style={{ marginBottom: 20 }}>
        <Typography.Title level={isMobile ? 4 : 3} style={{ marginBottom: 4, fontWeight: 700 }}>日志中心</Typography.Title>
        <Typography.Text type="secondary">集中查看登录、节点配置、批量操作与通知发送记录。</Typography.Text>
      </div>

      <Tabs
        items={[
          {
            key: "activity",
            label: "操作审计",
            children: (
              <Card bordered={false} style={{ borderRadius: 16 }} bodyStyle={{ padding: useCardList ? 12 : 24 }}>
                <Space wrap style={{ marginBottom: 16, width: "100%" }}>
                  <Select value={category} options={activityCategoryOptions} style={{ width: useCardList ? "100%" : 150 }} onChange={(value) => setCategory(value)} />
                  <Input
                    allowClear
                    prefix={<SearchOutlined />}
                    placeholder="搜索摘要、操作人或目标"
                    value={keyword}
                    onChange={(event) => setKeyword(event.target.value)}
                    onPressEnter={() => void loadActivity(1, activityPageSize, true)}
                    style={{ width: useCardList ? "100%" : 260 }}
                  />
                  <Button icon={<ReloadOutlined />} onClick={() => void loadActivity(1, activityPageSize, true)}>刷新</Button>
                </Space>
                {useCardList ? renderActivityList() : (
                  <Table
                    rowKey="id"
                    loading={activityLoading}
                    columns={activityColumns}
                    dataSource={activityRows}
                    scroll={{ x: 1100 }}
                    pagination={{
                      current: activityPage,
                      pageSize: activityPageSize,
                      total: activityTotal,
                      showSizeChanger: true,
                      onChange: (page, perPage) => void loadActivity(page, perPage, true),
                    }}
                  />
                )}
              </Card>
            ),
          },
          {
            key: "notifications",
            label: "通知发送",
            children: (
              <Card bordered={false} style={{ borderRadius: 16 }} bodyStyle={{ padding: useCardList ? 12 : 24 }}>
                <Space wrap style={{ marginBottom: 16, width: "100%" }}>
                  <Select value={notifyStatus} options={STATUS_OPTIONS} style={{ width: useCardList ? "100%" : 140 }} onChange={(value) => setNotifyStatus(value)} />
                  <Select value={eventType} options={EVENT_OPTIONS} style={{ width: useCardList ? "100%" : 150 }} onChange={(value) => setEventType(value)} />
                  <Button icon={<ReloadOutlined />} onClick={() => void loadNotifications(1, notificationPageSize, true)}>刷新</Button>
                </Space>
                {useCardList ? renderNotificationList() : (
                  <Table
                    rowKey="id"
                    loading={notificationLoading}
                    columns={notificationColumns}
                    dataSource={notificationRows}
                    scroll={{ x: 1250 }}
                    pagination={{
                      current: notificationPage,
                      pageSize: notificationPageSize,
                      total: notificationTotal,
                      showSizeChanger: true,
                      onChange: (page, perPage) => void loadNotifications(page, perPage, true),
                    }}
                  />
                )}
              </Card>
            ),
          },
        ]}
      />

      <Drawer title={activeDetail?.title || "日志详情"} open={detailOpen} onClose={() => setDetailOpen(false)} width={isMobile ? "100%" : 560}>
        <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0, lineHeight: 1.7 }}>
          {activeDetail?.content}
        </pre>
      </Drawer>
    </div>
  );
}
