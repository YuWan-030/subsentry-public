import { useEffect, useState } from "react";
import { Button, Card, Drawer, Form, Grid, Input, List, Modal, Popconfirm, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { DeleteOutlined, EditOutlined, KeyOutlined, SafetyCertificateOutlined, SafetyOutlined, SyncOutlined, UserSwitchOutlined } from "@ant-design/icons";
import { useAuth } from "../api/auth";
import { createUser, deleteUser, fetchUserAudit, fetchUsers, resetUserPassword, toggleUserEnabled, updateUserNickname, updateUserRole, type UserRow } from "../api/users";
import { extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess, notifyActionWarning, notifyDataLoaded } from "../utils/feedback";

const { useBreakpoint } = Grid;

type UserCreateFormValues = {
  username: string;
  nickname?: string;
  password: string;
  role: "admin" | "user";
};

type NicknameFormValues = {
  nickname?: string;
};

type RoleFormValues = {
  role: "admin" | "user";
};

export default function UsersPage() {
  const { user } = useAuth();
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const isCompactDesktop = !isMobile && screens.xl === false;
  const useCardList = isMobile || isCompactDesktop;

  const [userForm] = Form.useForm<UserCreateFormValues>();
  const [nicknameForm] = Form.useForm<NicknameFormValues>();
  const [roleForm] = Form.useForm<RoleFormValues>();
  const [userRows, setUserRows] = useState<UserRow[]>([]);
  const [activeUser, setActiveUser] = useState<UserRow | null>(null);
  const [roleModalOpen, setRoleModalOpen] = useState(false);
  const [nicknameModalOpen, setNicknameModalOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [roleFilter, setRoleFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [auditDrawerOpen, setAuditDrawerOpen] = useState(false);
  const [auditRows, setAuditRows] = useState<any[]>([]);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [roleSubmitting, setRoleSubmitting] = useState(false);
  const [nicknameSubmitting, setNicknameSubmitting] = useState(false);

  const loadData = async (p: number = page, ps: number = pageSize, showSuccess = false) => {
    setLoading(true);
    try {
      const res = await fetchUsers({ page: p, per_page: ps, keyword: keyword || undefined, role: roleFilter || undefined });
      setUserRows(res.items || []);
      setTotal(res.total || 0);
      setPage(res.page || p);
      setPageSize(res.per_page || ps);
      if (showSuccess) {
        notifyDataLoaded("users-load", `用户列表已刷新，共 ${res.total || 0} 条`);
      }
    } catch (error: any) {
      notifyActionError("users-load", extractErrorMessage(error, "加载用户列表失败"));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData(1, pageSize, false);
  }, []);

  const submitUser = async () => {
    try {
      const values = await userForm.validateFields();
      setCreateSubmitting(true);
      notifyActionLoading("user-create", "创建用户中...");
      const result = await createUser(values);
      notifyActionSuccess("user-create", result.message || "创建用户成功");
      userForm.resetFields();
      setCreateOpen(false);
      await loadData(page, pageSize, false);
    } catch (error: any) {
      if (error?.errorFields) {
        notifyActionWarning("user-create", `表单中有 ${error.errorFields.length} 项需要处理`);
        return;
      }
      notifyActionError("user-create", extractErrorMessage(error, "创建用户失败"));
    } finally {
      setCreateSubmitting(false);
    }
  };

  const submitRoleChange = async () => {
    if (!activeUser) {
      return;
    }
    try {
      const values = await roleForm.validateFields();
      setRoleSubmitting(true);
      notifyActionLoading("user-role", "修改角色中...");
      const result = await updateUserRole(activeUser.id, values.role);
      notifyActionSuccess("user-role", result.message || "用户角色已更新");
      setRoleModalOpen(false);
      roleForm.resetFields();
      await loadData(page, pageSize, false);
    } catch (error: any) {
      if (error?.errorFields) {
        notifyActionWarning("user-role", "请选择用户角色");
        return;
      }
      notifyActionError("user-role", extractErrorMessage(error, "修改角色失败"));
    } finally {
      setRoleSubmitting(false);
    }
  };

  const submitNicknameChange = async () => {
    if (!activeUser) {
      return;
    }
    try {
      const values = await nicknameForm.validateFields();
      setNicknameSubmitting(true);
      notifyActionLoading("user-nickname", "更新客户经理昵称中...");
      const result = await updateUserNickname(activeUser.id, values.nickname || "");
      notifyActionSuccess("user-nickname", result.message || "客户经理昵称已更新");
      setNicknameModalOpen(false);
      nicknameForm.resetFields();
      await loadData(page, pageSize, false);
    } catch (error: any) {
      if (error?.errorFields) {
        return;
      }
      notifyActionError("user-nickname", extractErrorMessage(error, "更新客户经理昵称失败"));
    } finally {
      setNicknameSubmitting(false);
    }
  };

  const handleResetPassword = async (row: UserRow) => {
    try {
      notifyActionLoading("user-reset-password", `重置 ${row.username} 密码中...`);
      const result = await resetUserPassword(row.id);
      notifyActionSuccess("user-reset-password", `已重置 ${row.username} 的密码`);
      Modal.success({
        title: "密码已重置",
        content: `用户 [${row.username}] 的新密码：${result.default_password || result.message}`,
      });
      await loadData(page, pageSize, false);
    } catch (error: any) {
      notifyActionError("user-reset-password", extractErrorMessage(error, "密码重置失败"));
    }
  };

  const handleToggleEnabled = async (row: UserRow) => {
    try {
      notifyActionLoading("user-enabled", `${row.enabled ? "禁用" : "启用"}用户中...`);
      const result = await toggleUserEnabled(row.id, !row.enabled);
      notifyActionSuccess("user-enabled", result.message || "状态更新成功");
      await loadData(page, pageSize, false);
    } catch (error: any) {
      notifyActionError("user-enabled", extractErrorMessage(error, "状态更新失败"));
    }
  };

  const handleDeleteUser = async (row: UserRow) => {
    try {
      notifyActionLoading("user-delete", `删除用户 ${row.username} 中...`);
      const result = await deleteUser(row.id);
      notifyActionSuccess("user-delete", result.message || "用户已删除");
      await loadData(page, pageSize, false);
    } catch (error: any) {
      notifyActionError("user-delete", extractErrorMessage(error, "删除用户失败"));
    }
  };

  const openAudit = async (row: UserRow) => {
    setActiveUser(row);
    setAuditDrawerOpen(true);
    setAuditRows([]);
    try {
      const rows = await fetchUserAudit(row.id);
      setAuditRows(rows || []);
      notifyDataLoaded("user-audit", `已加载 ${row.username} 的审计日志`);
    } catch (error: any) {
      notifyActionError("user-audit", extractErrorMessage(error, "加载审计日志失败"));
    }
  };

  if (user?.role !== "admin") {
    return (
      <Card style={{ borderRadius: 16, textAlign: "center", padding: "40px 20px" }}>
        <Typography.Title level={4} type="danger">权限受限</Typography.Title>
        <Typography.Paragraph type="secondary">当前账号无权访问用户管理，仅管理员可见。</Typography.Paragraph>
      </Card>
    );
  }

  const columns: ColumnsType<UserRow> = [
    { title: "用户名", dataIndex: "username", key: "username", width: 160, fixed: "left" },
    {
      title: "客户经理昵称",
      dataIndex: "nickname",
      key: "nickname",
      width: 180,
      render: (value, row) => value || row.username,
    },
    {
      title: "角色",
      dataIndex: "role",
      key: "role",
      width: 120,
      render: (role) => <Tag color={role === "admin" ? "purple" : "blue"}>{role === "admin" ? "管理员" : "普通用户"}</Tag>,
    },
    {
      title: "状态",
      dataIndex: "enabled",
      key: "enabled",
      width: 120,
      render: (enabled) => <Tag color={enabled ? "green" : "red"}>{enabled ? "启用" : "禁用"}</Tag>,
    },
    { title: "创建时间", dataIndex: "created_at", key: "created_at", width: 180 },
    {
      title: "操作",
      key: "action",
      width: 420,
      fixed: "right",
      render: (_: unknown, row: UserRow) => (
        <Space wrap>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setActiveUser(row);
              nicknameForm.setFieldsValue({ nickname: row.nickname || "" });
              setNicknameModalOpen(true);
            }}
          >
            改经理昵称
          </Button>
          <Button size="small" onClick={() => { setActiveUser(row); roleForm.setFieldsValue({ role: row.role }); setRoleModalOpen(true); }}>改角色</Button>
          <Button size="small" onClick={() => void handleResetPassword(row)}>重置密码</Button>
          <Button size="small" disabled={row.username === user?.username && row.enabled} onClick={() => void handleToggleEnabled(row)}>{row.enabled ? "禁用" : "启用"}</Button>
          <Button size="small" onClick={() => void openAudit(row)}>审计</Button>
          <Popconfirm title="确认删除该用户？" okText="删除" cancelText="取消" onConfirm={() => void handleDeleteUser(row)}>
            <Button danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ minWidth: 0, overflowX: "hidden" }}>
      <div style={{ marginBottom: 20 }}>
        <Typography.Title level={isMobile ? 4 : 3} style={{ marginBottom: 4, fontWeight: 700 }}>用户管理</Typography.Title>
        <Typography.Paragraph style={{ marginBottom: 0, color: "#64748b", fontSize: isMobile ? 12 : 14 }}>
          为每个注册用户维护登录权限与客户经理昵称。客户经理昵称会同步作为该用户名下客户的归属显示。
        </Typography.Paragraph>
      </div>

      <Card bordered={false} style={{ marginBottom: 16, borderRadius: 16 }}>
        <Space wrap style={{ width: "100%" }}>
          <Input.Search allowClear placeholder="按用户名搜索" value={keyword} onChange={(e) => setKeyword(e.target.value)} onSearch={() => void loadData(1, pageSize, true)} style={{ width: useCardList ? "100%" : 220 }} />
          <Select allowClear placeholder="按角色筛选" value={roleFilter} onChange={(v) => { setRoleFilter(v || undefined); void loadData(1, pageSize, true); }} options={[{ value: "admin", label: "管理员" }, { value: "user", label: "普通用户" }]} style={{ width: useCardList ? "calc(100% - 56px)" : 140 }} />
          <Button type="primary" onClick={() => { userForm.resetFields(); userForm.setFieldsValue({ role: "user" }); setCreateOpen(true); }}>新增用户</Button>
          <Button icon={<SyncOutlined spin={loading} />} onClick={() => void loadData(1, pageSize, true)} />
        </Space>
      </Card>

      {useCardList ? (
        <List
          loading={loading}
          dataSource={userRows}
          renderItem={(item) => (
            <Card style={{ marginBottom: 12, borderRadius: 16 }}>
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space wrap>
                  <Typography.Text strong>{item.username}</Typography.Text>
                  <Tag color="processing">经理昵称：{item.nickname || item.username}</Tag>
                  <Tag color={item.role === "admin" ? "purple" : "blue"}>{item.role === "admin" ? "管理员" : "普通用户"}</Tag>
                  <Tag color={item.enabled ? "green" : "red"}>{item.enabled ? "启用" : "禁用"}</Tag>
                </Space>
                <Typography.Text type="secondary">创建于：{item.created_at || "--"}</Typography.Text>
                <Space wrap>
                  <Button size="small" icon={<EditOutlined />} onClick={() => { setActiveUser(item); nicknameForm.setFieldsValue({ nickname: item.nickname || "" }); setNicknameModalOpen(true); }}>改经理昵称</Button>
                  <Button size="small" icon={<UserSwitchOutlined />} onClick={() => { setActiveUser(item); roleForm.setFieldsValue({ role: item.role }); setRoleModalOpen(true); }}>改角色</Button>
                  <Button size="small" icon={<KeyOutlined />} onClick={() => void handleResetPassword(item)}>重置密码</Button>
                  <Button size="small" icon={<SafetyCertificateOutlined />} disabled={item.username === user?.username && item.enabled} onClick={() => void handleToggleEnabled(item)}>{item.enabled ? "禁用" : "启用"}</Button>
                  <Button size="small" icon={<SafetyOutlined />} onClick={() => void openAudit(item)}>审计</Button>
                  <Popconfirm title="确认删除该用户？" okText="删除" cancelText="取消" onConfirm={() => void handleDeleteUser(item)}>
                    <Button danger size="small" icon={<DeleteOutlined />}>删除</Button>
                  </Popconfirm>
                </Space>
              </Space>
            </Card>
          )}
          pagination={{
            current: page,
            pageSize,
            total,
            size: "small",
            onChange: (p, ps) => void loadData(p, ps, true),
          }}
        />
      ) : (
        <Table
          rowKey="id"
          loading={loading}
          scroll={{ x: 1200 }}
          columns={columns}
          dataSource={userRows}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            onChange: (p, ps) => void loadData(p, ps, true),
          }}
          style={{ borderRadius: 12, overflow: "hidden" }}
        />
      )}

      <Modal open={roleModalOpen} title={`修改角色${activeUser ? `：${activeUser.username}` : ""}`} onCancel={() => setRoleModalOpen(false)} onOk={submitRoleChange} confirmLoading={roleSubmitting} destroyOnClose>
        <Form form={roleForm} layout="vertical">
          <Form.Item name="role" label="角色" rules={[{ required: true, message: "请选择角色" }]}>
            <Select options={[{ value: "user", label: "普通用户" }, { value: "admin", label: "管理员" }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal open={nicknameModalOpen} title={`修改客户经理昵称${activeUser ? `：${activeUser.username}` : ""}`} onCancel={() => setNicknameModalOpen(false)} onOk={submitNicknameChange} confirmLoading={nicknameSubmitting} destroyOnClose>
        <Form form={nicknameForm} layout="vertical">
          <Form.Item name="nickname" label="客户经理昵称">
            <Input placeholder="例如：林" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal open={createOpen} title="新增用户" onCancel={() => setCreateOpen(false)} onOk={submitUser} confirmLoading={createSubmitting} okText="创建" destroyOnClose>
        <Form form={userForm} layout="vertical" initialValues={{ role: "user" }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input placeholder="例如：lin" />
          </Form.Item>
          <Form.Item name="nickname" label="客户经理昵称">
            <Input placeholder="例如：林" />
          </Form.Item>
          <Form.Item name="password" label="初始密码" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password placeholder="请输入初始密码" />
          </Form.Item>
          <Form.Item name="role" label="角色">
            <Select options={[{ value: "user", label: "普通用户" }, { value: "admin", label: "管理员" }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer title={activeUser ? `用户审计日志：${activeUser.username}` : "用户审计日志"} open={auditDrawerOpen} onClose={() => setAuditDrawerOpen(false)} width={isMobile ? "100%" : 540}>
        <Table
          rowKey="id"
          dataSource={auditRows}
          size="small"
          columns={[
            { title: "时间", dataIndex: "created_at", key: "created_at", width: 150 },
            { title: "动作", dataIndex: "action", key: "action", width: 120 },
            { title: "描述", dataIndex: "change_summary", key: "change_summary" },
          ]}
          pagination={{ pageSize: 10 }}
        />
      </Drawer>
    </div>
  );
}
