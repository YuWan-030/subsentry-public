import { useEffect, useState } from "react";
import { Button, Card, DatePicker, Form, Grid, Input, InputNumber, List, Modal, Popconfirm, Select, Space, Statistic, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { DeleteOutlined, EditOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  deleteFinancialLog,
  fetchFinancialLogs,
  updateFinancialLog,
  type FinancialLogRow,
  type FinancialLogUpdatePayload,
} from "../api/finance";
import { fetchSettingsOptions, type SettingsOptions } from "../api/settings";
import { extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess, notifyDataLoaded } from "../utils/feedback";

const { RangePicker } = DatePicker;
const { useBreakpoint } = Grid;

let cachedFinanceOptions: Pick<SettingsOptions, "nodes" | "managers"> | null = null;

function formatCurrency(value?: number) {
  return `¥${Number(value || 0).toFixed(2)}`;
}

export default function FinancePage() {
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const isCompactDesktop = !isMobile && screens.xl === false;
  const useCardList = isMobile || isCompactDesktop;
  const [rows, setRows] = useState<FinancialLogRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [totalAmount, setTotalAmount] = useState(0);
  const [keyword, setKeyword] = useState("");
  const [ownerUsername, setOwnerUsername] = useState("");
  const [nodeId, setNodeId] = useState<number | undefined>();
  const [dateRange, setDateRange] = useState<[string, string] | null>(null);
  const [optionLoading, setOptionLoading] = useState(false);
  const [managerOptions, setManagerOptions] = useState<Array<{ label: string; value: string }>>([]);
  const [nodeOptions, setNodeOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [editingRow, setEditingRow] = useState<FinancialLogRow | null>(null);
  const [form] = Form.useForm<FinancialLogUpdatePayload>();

  const loadOptions = async () => {
    if (cachedFinanceOptions) {
      setManagerOptions(cachedFinanceOptions.managers.map((item: any) => ({ label: item.nickname || item.name || item.username, value: item.username || item.name })));
      setNodeOptions(cachedFinanceOptions.nodes.map((item) => ({ label: item.name, value: item.id })));
      return;
    }
    setOptionLoading(true);
    try {
      const options = await fetchSettingsOptions();
      cachedFinanceOptions = { nodes: options.nodes || [], managers: options.managers || [] };
      setManagerOptions(cachedFinanceOptions.managers.map((item: any) => ({ label: item.nickname || item.name || item.username, value: item.username || item.name })));
      setNodeOptions(cachedFinanceOptions.nodes.map((item) => ({ label: item.name, value: item.id })));
    } catch (error: any) {
      notifyActionError("finance-options-load", extractErrorMessage(error, "加载筛选选项失败"));
    } finally {
      setOptionLoading(false);
    }
  };

  const loadRows = async (nextPage = page, nextPageSize = pageSize, showSuccess = false) => {
    setLoading(true);
    try {
      const data = await fetchFinancialLogs({
        page: nextPage,
        per_page: nextPageSize,
        keyword,
        owner_username: ownerUsername,
        node_id: nodeId || "",
        date_from: dateRange?.[0] || "",
        date_to: dateRange?.[1] || "",
      });
      setRows(data.items || []);
      setTotal(data.total || 0);
      setPage(data.page || nextPage);
      setPageSize(data.per_page || nextPageSize);
      setTotalAmount(Number(data.total_amount || 0));
      if (showSuccess) {
        notifyDataLoaded("finance-logs-load", `财务流水已刷新，共 ${data.total || 0} 条`);
      }
    } catch (error: any) {
      notifyActionError("finance-logs-load", extractErrorMessage(error, "加载财务流水失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadOptions();
    void loadRows(1, pageSize, false);
  }, []);

  const search = () => {
    void loadRows(1, pageSize, true);
  };

  const openEdit = (row: FinancialLogRow) => {
    setEditingRow(row);
    form.setFieldsValue({
      customer_name: row.customer_name,
      owner_username: row.owner_username || "",
      renew_price: row.renew_price,
      amount: Number(row.amount || 0),
      renew_days: row.renew_days,
      new_expiry: row.new_expiry,
      created_at: row.created_at,
    });
  };

  const saveEdit = async () => {
    if (!editingRow) {
      return;
    }
    const values = await form.validateFields();
    try {
      setSaving(true);
      notifyActionLoading("finance-log-save", "正在保存财务流水...");
      const result = await updateFinancialLog(editingRow.id, values);
      notifyActionSuccess("finance-log-save", result.message || "财务流水已更新");
      setEditingRow(null);
      await loadRows(page, pageSize, false);
    } catch (error: any) {
      notifyActionError("finance-log-save", extractErrorMessage(error, "保存财务流水失败"));
    } finally {
      setSaving(false);
    }
  };

  const removeRow = async (row: FinancialLogRow) => {
    try {
      notifyActionLoading("finance-log-delete", `正在删除 ${row.customer_name} 的流水...`);
      const result = await deleteFinancialLog(row.id);
      notifyActionSuccess("finance-log-delete", result.message || "财务流水已删除");
      await loadRows(page, pageSize, false);
    } catch (error: any) {
      notifyActionError("finance-log-delete", extractErrorMessage(error, "删除财务流水失败"));
    }
  };

  const columns: ColumnsType<FinancialLogRow> = [
    { title: "时间", dataIndex: "created_at", key: "created_at", width: 170 },
    { title: "客户", dataIndex: "customer_name", key: "customer_name", width: 160, render: (value) => value || "-" },
    { title: "客户经理", dataIndex: "owner_username", key: "owner_username", width: 130, render: (value) => value || "-" },
    { title: "集群节点", dataIndex: "node_name", key: "node_name", width: 130, render: (value, row) => value || row.node_id || "-" },
    { title: "远端标识", dataIndex: "remote_email", key: "remote_email", width: 180, render: (value) => value || "-" },
    { title: "续费价格", dataIndex: "renew_price", key: "renew_price", width: 130, render: (value) => <Tag>{value || "-"}</Tag> },
    { title: "金额", dataIndex: "amount", key: "amount", width: 110, render: (value) => <Typography.Text strong>{formatCurrency(value)}</Typography.Text> },
    { title: "天数", dataIndex: "renew_days", key: "renew_days", width: 90 },
    { title: "新到期", dataIndex: "new_expiry", key: "new_expiry", width: 130 },
    {
      title: "操作",
      key: "action",
      width: 150,
      align: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>修改</Button>
          <Popconfirm title="确认删除这条财务流水？" okText="删除" cancelText="取消" onConfirm={() => void removeRow(row)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const renderMobileList = () => (
    <List
      loading={loading}
      dataSource={rows}
      renderItem={(row) => (
        <Card bordered={false} style={{ borderRadius: 16, marginBottom: 12 }} bodyStyle={{ padding: 14 }}>
          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            <Space wrap>
              <Tag>{row.renew_price || "-"}</Tag>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>{row.created_at}</Typography.Text>
            </Space>
            <Typography.Text strong>{row.customer_name}</Typography.Text>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 8, alignItems: "end" }}>
              <Space direction="vertical" size={2}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>客户经理：{row.owner_username || "-"}</Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>节点：{row.node_name || row.node_id || "-"} / 天数：{row.renew_days}</Typography.Text>
              </Space>
              <Typography.Text strong style={{ fontSize: 18 }}>{formatCurrency(row.amount)}</Typography.Text>
            </div>
            <Space wrap size={8}>
              <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>修改</Button>
              <Popconfirm title="确认删除这条财务流水？" okText="删除" cancelText="取消" onConfirm={() => void removeRow(row)}>
                <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
              </Popconfirm>
            </Space>
          </Space>
        </Card>
      )}
      pagination={{ current: page, pageSize, total, size: "small", onChange: (nextPage, nextPageSize) => void loadRows(nextPage, nextPageSize, true) }}
    />
  );

  return (
    <div style={{ minWidth: 0, overflowX: "hidden" }}>
      <div style={{ marginBottom: 20 }}>
        <Typography.Title level={isMobile ? 4 : 3} style={{ marginBottom: 4, fontWeight: 700 }}>财务流水</Typography.Title>
        <Typography.Text type="secondary">查看和维护客户续费产生的收入流水，修改或删除后会刷新总览收入统计。</Typography.Text>
      </div>

      <Card bordered={false} style={{ borderRadius: 16, marginBottom: 16 }} bodyStyle={{ padding: useCardList ? 12 : 20 }}>
        <Space direction="vertical" size={useCardList ? 12 : 16} style={{ width: "100%" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: useCardList ? "1fr 1fr" : "minmax(220px, 1.4fr) minmax(150px, 0.8fr) minmax(150px, 0.8fr) minmax(280px, 1.4fr) auto auto",
              gap: useCardList ? 8 : 10,
              alignItems: "center",
            }}
          >
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索客户、价格、邮箱或经理"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onPressEnter={search}
              style={{ gridColumn: useCardList ? "1 / -1" : undefined }}
            />
            <Select
              allowClear
              showSearch
              loading={optionLoading}
              placeholder="客户经理"
              optionFilterProp="label"
              value={ownerUsername}
              options={managerOptions}
              onChange={(value) => setOwnerUsername(value || "")}
            />
            <Select
              allowClear
              showSearch
              loading={optionLoading}
              placeholder="集群节点"
              optionFilterProp="label"
              value={nodeId}
              options={nodeOptions}
              onChange={(value) => setNodeId(value)}
            />
            <RangePicker
              showTime
              inputReadOnly={isMobile}
              style={{ width: "100%", gridColumn: useCardList ? "1 / -1" : undefined }}
              onChange={(values) => {
                setDateRange(values ? [values[0]?.format("YYYY-MM-DD HH:mm:ss") || "", values[1]?.format("YYYY-MM-DD HH:mm:ss") || ""] : null);
              }}
            />
            <Button type="primary" icon={<SearchOutlined />} onClick={search}>查询</Button>
            <Button icon={<ReloadOutlined />} onClick={() => void loadRows(page, pageSize, true)}>刷新</Button>
          </div>
          <Statistic title="筛选合计" value={totalAmount} precision={2} prefix="¥" />
        </Space>
      </Card>

      <Card bordered={false} style={{ borderRadius: 16 }} bodyStyle={{ padding: useCardList ? 12 : 24 }}>
        {useCardList ? renderMobileList() : (
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={rows}
            scroll={{ x: 1250 }}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              showTotal: (value) => `共 ${value} 条`,
              onChange: (nextPage, nextPageSize) => void loadRows(nextPage, nextPageSize, true),
            }}
          />
        )}
      </Card>

      <Modal
        title="修改财务流水"
        open={Boolean(editingRow)}
        onCancel={() => setEditingRow(null)}
        onOk={() => void saveEdit()}
        confirmLoading={saving}
        width={isMobile ? "96%" : 560}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="customer_name" label="客户名称" rules={[{ required: true, message: "请输入客户名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="owner_username" label="客户经理">
            <Input />
          </Form.Item>
          <Form.Item name="renew_price" label="续费价格" rules={[{ required: true, message: "请输入续费价格" }]}>
            <Input />
          </Form.Item>
          <Space.Compact block>
            <Form.Item name="amount" label="金额" rules={[{ required: true, message: "请输入金额" }]} style={{ width: "50%" }}>
              <InputNumber min={0} precision={2} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item name="renew_days" label="续费天数" rules={[{ required: true, message: "请输入续费天数" }]} style={{ width: "50%" }}>
              <InputNumber style={{ width: "100%" }} />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="new_expiry" label="新到期" rules={[{ required: true, message: "请输入新到期时间" }]}>
            <Input placeholder="YYYY-MM-DD 或 无限期" />
          </Form.Item>
          <Form.Item name="created_at" label="流水时间" rules={[{ required: true, message: "请输入流水时间" }]}>
            <Input placeholder="YYYY-MM-DD HH:mm:ss" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
