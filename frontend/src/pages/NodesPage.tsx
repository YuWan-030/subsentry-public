import { useEffect, useState } from "react";
import { Button, Card, Divider, Form, Grid, Input, InputNumber, List, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { DeleteOutlined, EditOutlined, PlusOutlined, SyncOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { addNode, deleteNode, fetchNodeSubscriptionSettings, fetchSettingsOptions, probeNode, testNode, updateNode, type NodePayload } from "../api/settings";
import { extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess, notifyDataLoaded } from "../utils/feedback";
import { formatDateTimeText } from "../utils/display";

const { useBreakpoint } = Grid;

type NodeRow = {
  id: number;
  name: string;
  display_name: string;
  scheme: string;
  address: string;
  port: number;
  base_path: string;
  subscription_scheme: "http" | "https";
  subscription_address: string;
  subscription_port: number;
  subscription_sub_path: string;
  subscription_json_path: string;
  subscription_clash_path: string;
  allow_insecure: boolean;
  last_status: string;
  last_message: string;
  last_checked_at?: string;
  last_latency_ms?: number;
};

export default function NodesPage() {
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [loadingSubscription, setLoadingSubscription] = useState(false);
  const [probeLoadingId, setProbeLoadingId] = useState<number | null>(null);
  const [nodes, setNodes] = useState<NodeRow[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingNode, setEditingNode] = useState<NodeRow | null>(null);
  const [form] = Form.useForm<NodePayload>();

  const loadData = async (showSuccess = false) => {
    setLoading(true);
    try {
      const options = await fetchSettingsOptions();
      setNodes(options.nodes || []);
      if (showSuccess) {
        notifyDataLoaded("nodes-refresh", "节点列表已刷新");
      }
    } catch (error: any) {
      notifyActionError("nodes-refresh", extractErrorMessage(error, "加载节点失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData(false);
  }, []);

  const openCreate = () => {
    setEditingNode(null);
    form.resetFields();
    form.setFieldsValue({
      scheme: "https",
      port: 2053,
      base_path: "/",
      allow_insecure: false,
      subscription_scheme: "https",
      subscription_port: 10882,
      subscription_sub_path: "/sub",
      subscription_json_path: "/json",
      subscription_clash_path: "/clash",
    });
    setModalOpen(true);
  };

  const openEdit = (row: NodeRow) => {
    setEditingNode(row);
    form.setFieldsValue({
      name: row.name,
      scheme: row.scheme as "http" | "https",
      address: row.address,
      port: row.port,
      base_path: row.base_path,
      api_token: "",
      allow_insecure: row.allow_insecure,
      subscription_scheme: row.subscription_scheme || row.scheme as "http" | "https",
      subscription_address: row.subscription_address || row.address,
      subscription_port: row.subscription_port || 10882,
      subscription_sub_path: row.subscription_sub_path || "/sub",
      subscription_json_path: row.subscription_json_path || "/json",
      subscription_clash_path: row.subscription_clash_path || "/clash",
    });
    setModalOpen(true);
  };

  const handleProbe = async (row: NodeRow) => {
    setProbeLoadingId(row.id);
    try {
      notifyActionLoading(`node-probe-${row.id}`, `探测节点 ${row.display_name || row.name} 中...`);
      const result = await probeNode(row.id);
      notifyActionSuccess(`node-probe-${row.id}`, result.message || "节点探测成功");
      await loadData(false);
    } catch (error: any) {
      notifyActionError(`node-probe-${row.id}`, extractErrorMessage(error, "节点探测失败"));
      await loadData(false);
    } finally {
      setProbeLoadingId(null);
    }
  };

  const submitNode = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      notifyActionLoading("node-save", editingNode ? "更新节点中..." : "添加节点中...");
      if (editingNode) {
        const result = await updateNode(editingNode.id, values);
        notifyActionSuccess("node-save", result.message || "节点更新成功");
      } else {
        const result = await addNode(values);
        notifyActionSuccess("node-save", result.message || "节点添加成功");
      }
      setModalOpen(false);
      await loadData(false);
    } catch (error: any) {
      notifyActionError("node-save", extractErrorMessage(error, "保存节点失败"));
    } finally {
      setSaving(false);
    }
  };

  const validateCurrentPanel = async () => {
    const values = await form.validateFields();
    try {
      setTesting(true);
      notifyActionLoading("node-test", "验证面板连接中...");
      const result = await testNode(values);
      notifyActionSuccess("node-test", result.message || "连接验证通过");
    } catch (error: any) {
      notifyActionError("node-test", extractErrorMessage(error, "连接验证失败"));
    } finally {
      setTesting(false);
    }
  };

  const loadSubscriptionFromPanel = async () => {
    const values = await form.validateFields(["name", "scheme", "address", "port", "base_path", "api_token", "allow_insecure"]);
    try {
      setLoadingSubscription(true);
      notifyActionLoading("node-subscription-settings", "读取订阅配置中...");
      const result = await fetchNodeSubscriptionSettings({
        ...form.getFieldsValue(),
        ...values,
      });
      form.setFieldsValue(result.data);
      notifyActionSuccess("node-subscription-settings", result.message || "订阅配置已读取");
    } catch (error: any) {
      notifyActionError("node-subscription-settings", extractErrorMessage(error, "读取订阅配置失败"));
    } finally {
      setLoadingSubscription(false);
    }
  };

  const removeNodeRow = async (row: NodeRow) => {
    try {
      notifyActionLoading("node-delete", `删除节点 ${row.display_name || row.name} 中...`);
      const result = await deleteNode(row.id);
      notifyActionSuccess("node-delete", result.message || "节点删除成功");
      await loadData(false);
    } catch (error: any) {
      notifyActionError("node-delete", extractErrorMessage(error, "删除节点失败"));
    }
  };

  const columns: ColumnsType<NodeRow> = [
    {
      title: "节点名称",
      dataIndex: "display_name",
      key: "display_name",
      render: (_, row) => (
        <div>
          <div style={{ fontWeight: 600 }}>{row.display_name || row.name}</div>
          <Typography.Text type="secondary">
            {row.scheme}://{row.address}:{row.port}{row.base_path}
          </Typography.Text>
          <br />
          <Typography.Text type="secondary">
            订阅：{row.subscription_scheme || row.scheme}://{row.subscription_address || row.address}:{row.subscription_port || 10882}{row.subscription_sub_path || "/sub"}
          </Typography.Text>
        </div>
      ),
    },
    {
      title: "状态",
      key: "status",
      render: (_, row) => <Tag color={row.last_status === "online" ? "green" : row.last_status === "offline" ? "red" : "default"}>{row.last_status || "unknown"}</Tag>,
    },
    {
      title: "延迟",
      dataIndex: "last_latency_ms",
      key: "last_latency_ms",
      render: (value) => (value ? `${value} ms` : "-"),
    },
    {
      title: "最近校验",
      dataIndex: "last_checked_at",
      key: "last_checked_at",
      render: (value) => formatDateTimeText(value) || "-",
    },
    {
      title: "备注",
      dataIndex: "last_message",
      key: "last_message",
      render: (value) => value || "-",
    },
    {
      title: "操作",
      key: "action",
      render: (_, row) => (
        <Space>
          <Button icon={<ThunderboltOutlined />} loading={probeLoadingId === row.id} onClick={() => void handleProbe(row)} />
          <Button icon={<EditOutlined />} onClick={() => openEdit(row)} />
          <Popconfirm title="确定删除该节点？" description="删除前请先清理该节点下的远程客户映射。" onConfirm={() => void removeNodeRow(row)} okText="删除" cancelText="取消">
            <Button danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", justifyContent: "space-between", alignItems: isMobile ? "stretch" : "center", marginBottom: 20, gap: 12, flexWrap: "wrap" }}>
        <div>
          <Typography.Title level={isMobile ? 4 : 3} style={{ marginBottom: 4 }}>3X-UI 节点集群</Typography.Title>
          <Typography.Text type="secondary">
            节点创建后会自动显示为 `节点名称-[IP地址]`，方便你在集群和客户视图里快速识别。
          </Typography.Text>
        </div>
        <Space wrap style={{ width: isMobile ? "100%" : "auto" }}>
          <Button icon={<SyncOutlined />} onClick={() => void loadData(true)}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>添加节点</Button>
        </Space>
      </div>

      {isMobile ? (
        <List
          loading={loading}
          dataSource={nodes}
          renderItem={(row) => (
            <Card bordered={false} style={{ borderRadius: 16, marginBottom: 12 }} bodyStyle={{ padding: 14 }}>
              <Space direction="vertical" size={10} style={{ width: "100%" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                  <div style={{ minWidth: 0 }}>
                    <Typography.Text strong style={{ display: "block" }}>{row.display_name || row.name}</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 12, wordBreak: "break-all" }}>
                      {row.scheme}://{row.address}:{row.port}{row.base_path}
                    </Typography.Text>
                  </div>
                  <Tag color={row.last_status === "online" ? "green" : row.last_status === "offline" ? "red" : "default"}>{row.last_status || "unknown"}</Tag>
                </div>
                <Typography.Text type="secondary" style={{ fontSize: 12, wordBreak: "break-all" }}>
                  订阅：{row.subscription_scheme || row.scheme}://{row.subscription_address || row.address}:{row.subscription_port || 10882}{row.subscription_sub_path || "/sub"}
                </Typography.Text>
                <Space size={8} wrap>
                  <Tag>{row.last_latency_ms ? `${row.last_latency_ms} ms` : "未测速"}</Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>{formatDateTimeText(row.last_checked_at) || "未校验"}</Typography.Text>
                </Space>
                <Space wrap>
                  <Button size="small" icon={<ThunderboltOutlined />} loading={probeLoadingId === row.id} onClick={() => void handleProbe(row)}>探测</Button>
                  <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>编辑</Button>
                  <Popconfirm title="确定删除该节点？" description="删除前请先清理该节点下的远程客户映射。" onConfirm={() => void removeNodeRow(row)} okText="删除" cancelText="取消">
                    <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
                  </Popconfirm>
                </Space>
              </Space>
            </Card>
          )}
        />
      ) : (
        <Card bordered={false} style={{ borderRadius: 16 }}>
          <Table rowKey="id" loading={loading} columns={columns} dataSource={nodes} scroll={{ x: 1100 }} />
        </Card>
      )}

      <Modal
        open={modalOpen}
        title={editingNode ? "编辑节点" : "新增 3X-UI 节点"}
        onCancel={() => setModalOpen(false)}
        onOk={submitNode}
        confirmLoading={saving}
        okText={editingNode ? "保存" : "创建"}
        destroyOnClose
        width={isMobile ? "calc(100vw - 24px)" : 720}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="节点名称" rules={[{ required: true, message: "请输入节点名称" }]}>
            <Input placeholder="例如：洛杉矶A" />
          </Form.Item>
          <Typography.Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
            保存后展示名称会自动变成 `节点名称-[IP地址]`，例如 `洛杉矶A-[1.2.3.4]`。
          </Typography.Text>
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "140px 1fr 150px", gap: 12 }}>
            <Form.Item name="scheme" label="协议" rules={[{ required: true }]}>
              <Select options={[{ value: "https", label: "https" }, { value: "http", label: "http" }]} />
            </Form.Item>
            <Form.Item name="address" label="面板地址" rules={[{ required: true, message: "请输入面板域名或 IP" }]}>
              <Input placeholder="1.2.3.4 或 panel.example.com" />
            </Form.Item>
            <Form.Item name="port" label="端口" rules={[{ required: true, message: "请输入端口" }]}>
              <InputNumber min={1} style={{ width: "100%" }} />
            </Form.Item>
          </div>
          <Form.Item name="base_path" label="基础路径" rules={[{ required: true, message: "请输入基础路径" }]}>
            <Input placeholder="/" />
          </Form.Item>
          <Form.Item name="api_token" label={editingNode ? "API Token（留空表示不修改）" : "API Token"} rules={[{ required: !editingNode, message: "请输入 API Token" }]}>
            <Input.Password placeholder="3X-UI Settings -> Security -> API Token" />
          </Form.Item>
          <Form.Item name="allow_insecure" label="忽略 HTTPS 证书校验" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Divider orientation="left">订阅服务</Divider>
          <Typography.Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
            订阅服务经常和面板 API 使用不同端口。这里填写客户实际可访问的公网订阅地址。
          </Typography.Text>
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "140px 1fr 150px", gap: 12 }}>
            <Form.Item name="subscription_scheme" label="订阅协议" rules={[{ required: true }]}>
              <Select options={[{ value: "https", label: "https" }, { value: "http", label: "http" }]} />
            </Form.Item>
            <Form.Item name="subscription_address" label="订阅地址" rules={[{ required: true, message: "请输入订阅域名或 IP" }]}>
              <Input placeholder="留意这里应是客户可访问地址" />
            </Form.Item>
            <Form.Item name="subscription_port" label="订阅端口" rules={[{ required: true, message: "请输入订阅端口" }]}>
              <InputNumber min={1} style={{ width: "100%" }} />
            </Form.Item>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr 1fr", gap: 12 }}>
            <Form.Item name="subscription_sub_path" label="标准订阅路径" rules={[{ required: true }]}>
              <Input placeholder="/sub" />
            </Form.Item>
            <Form.Item name="subscription_json_path" label="JSON 路径" rules={[{ required: true }]}>
              <Input placeholder="/json" />
            </Form.Item>
            <Form.Item name="subscription_clash_path" label="Clash 路径" rules={[{ required: true }]}>
              <Input placeholder="/clash" />
            </Form.Item>
          </div>
          <Divider />
          <Space wrap style={{ width: "100%" }}>
            <Button loading={testing} onClick={() => void validateCurrentPanel()}>先验证连接</Button>
            <Button loading={loadingSubscription} onClick={() => void loadSubscriptionFromPanel()}>从面板读取订阅配置</Button>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
