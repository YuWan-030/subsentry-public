import { useEffect, useState } from "react";
import { Button, Card, Col, Descriptions, Empty, Grid, Row, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined } from "@ant-design/icons";
import { fetchSystemHealth, type HealthActivity, type HealthNode, type SystemHealth } from "../api/system";
import { formatDateTimeText } from "../utils/display";
import { extractErrorMessage, notifyActionError, notifyDataLoaded } from "../utils/feedback";

const { useBreakpoint } = Grid;

function statusMeta(status?: string) {
  const value = String(status || "unknown").toLowerCase();
  if (["online", "success", "ok"].includes(value)) {
    return { color: "green", text: "正常" };
  }
  if (["degraded", "partial", "skipped"].includes(value)) {
    return { color: "orange", text: value === "skipped" ? "已跳过" : "部分异常" };
  }
  if (["offline", "failed", "error"].includes(value)) {
    return { color: "red", text: "异常" };
  }
  return { color: "default", text: "未知" };
}

function StatusTag({ status }: { status?: string }) {
  const meta = statusMeta(status);
  return <Tag color={meta.color}>{meta.text}</Tag>;
}

function HealthCard({
  title,
  status,
  value,
  extra,
}: {
  title: string;
  status?: string;
  value: string;
  extra?: string;
}) {
  return (
    <Card bordered={false} style={{ borderRadius: 8, height: "100%" }} bodyStyle={{ padding: 18 }}>
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        <Space style={{ width: "100%", justifyContent: "space-between" }}>
          <Typography.Text type="secondary">{title}</Typography.Text>
          <StatusTag status={status} />
        </Space>
        <Typography.Title level={4} style={{ margin: 0 }}>
          {value}
        </Typography.Title>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {extra || "-"}
        </Typography.Text>
      </Space>
    </Card>
  );
}

function activityLabel(row?: HealthActivity | null) {
  if (!row) {
    return "暂无执行记录";
  }
  return row.summary || `${row.category}/${row.action}`;
}

export default function SystemHealthPage() {
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(false);

  const loadHealth = async (showSuccess = false) => {
    setLoading(true);
    try {
      const data = await fetchSystemHealth();
      setHealth(data);
      if (showSuccess) {
        notifyDataLoaded("system-health-refresh", "系统健康状态已刷新");
      }
    } catch (error: any) {
      notifyActionError("system-health-refresh", extractErrorMessage(error, "加载系统健康状态失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadHealth(false);
  }, []);

  const nodeColumns: ColumnsType<HealthNode> = [
    {
      title: "节点",
      dataIndex: "name",
      key: "name",
      render: (value, row) => (
        <div>
          <Typography.Text strong>{value || "-"}</Typography.Text>
          <br />
          <Typography.Text type="secondary">
            {row.address}
            {row.port ? `:${row.port}` : ""}
          </Typography.Text>
        </div>
      ),
    },
    { title: "状态", dataIndex: "status", key: "status", width: 100, render: (value) => <StatusTag status={value} /> },
    { title: "延迟", dataIndex: "latency_ms", key: "latency_ms", width: 100, render: (value) => (value ? `${value} ms` : "-") },
    { title: "最近探测", dataIndex: "last_checked_at", key: "last_checked_at", width: 170, render: (value) => formatDateTimeText(value) || "-" },
    { title: "结果", dataIndex: "message", key: "message", ellipsis: true, render: (value) => value || "-" },
  ];

  const latestTask = health?.latest_auto_task;
  const notificationCheck = health?.notification.last_check;

  return (
    <Space direction="vertical" size={18} style={{ width: "100%" }}>
      <Space align="center" style={{ width: "100%", justifyContent: "space-between" }}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            系统健康
          </Typography.Title>
          <Typography.Text type="secondary">运行状态、连接状态和自动任务最近结果</Typography.Text>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => void loadHealth(true)}>
          刷新
        </Button>
      </Space>

      <Row gutter={[12, 12]}>
        <Col xs={24} md={12} xl={6}>
          <HealthCard
            title="后端运行状态"
            status={health?.backend.status}
            value={health?.backend.message || "加载中"}
            extra={health ? `${health.backend.app_name} ${health.backend.version}，启动于 ${formatDateTimeText(health.backend.started_at)}` : ""}
          />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <HealthCard
            title="数据库连接状态"
            status={health?.database.status}
            value={health?.database.message || "加载中"}
            extra={health?.database.latency_ms !== undefined ? `响应 ${health.database.latency_ms} ms` : ""}
          />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <HealthCard
            title="节点探测状态"
            status={health?.nodes.status}
            value={health ? `${health.nodes.online}/${health.nodes.total} 在线` : "加载中"}
            extra={health ? `${health.nodes.offline} 离线，${health.nodes.unknown} 未知，最近 ${formatDateTimeText(health.nodes.latest_checked_at) || "暂无"}` : ""}
          />
        </Col>
        <Col xs={24} md={12} xl={6}>
          <HealthCard
            title="最近通知检查"
            status={health?.notification.status}
            value={formatDateTimeText(health?.notification.last_checked_at) || "暂无记录"}
            extra={health?.notification.message || ""}
          />
        </Col>
      </Row>

      <Card bordered={false} style={{ borderRadius: 8 }} bodyStyle={{ padding: 18 }}>
        <Descriptions
          title="自动任务执行结果"
          bordered
          size="small"
          column={isMobile ? 1 : 2}
          items={[
            {
              key: "latest-task",
              label: "最近一次自动任务",
              children: (
                <Space wrap>
                  <StatusTag status={latestTask?.status} />
                  <Typography.Text>{activityLabel(latestTask)}</Typography.Text>
                  <Typography.Text type="secondary">{formatDateTimeText(latestTask?.created_at) || "-"}</Typography.Text>
                </Space>
              ),
            },
            {
              key: "notification-check",
              label: "最近一次通知检查",
              children: (
                <Space wrap>
                  <StatusTag status={notificationCheck?.status} />
                  <Typography.Text>{activityLabel(notificationCheck)}</Typography.Text>
                  <Typography.Text type="secondary">{formatDateTimeText(notificationCheck?.created_at) || "-"}</Typography.Text>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Card bordered={false} style={{ borderRadius: 8 }} bodyStyle={{ padding: 18 }}>
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space style={{ width: "100%", justifyContent: "space-between" }}>
            <Typography.Title level={5} style={{ margin: 0 }}>
              节点探测明细
            </Typography.Title>
            <Typography.Text type="secondary">{health?.nodes.message || ""}</Typography.Text>
          </Space>
          {health?.nodes.items?.length ? (
            <Table
              rowKey="id"
              loading={loading}
              columns={nodeColumns}
              dataSource={health.nodes.items}
              pagination={false}
              size="middle"
              scroll={{ x: 760 }}
            />
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无节点探测记录" />
          )}
        </Space>
      </Card>
    </Space>
  );
}
