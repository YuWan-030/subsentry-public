import { useEffect, useState } from "react";
import { Button, Card, Col, Divider, Form, Grid, Input, List, Popconfirm, Row, Space, Tag, Typography } from "antd";
import { KeyOutlined, LinkOutlined, LoginOutlined, SaveOutlined, UserOutlined } from "@ant-design/icons";
import { changeMyPassword, deletePasskey, fetchOnAuthConfig, fetchPasskeys, finishPasskeyRegistration, startOnAuth, startPasskeyRegistration, unbindOnAuth, updateMyProfile, useAuth } from "../api/auth";
import { extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess, notifyActionWarning } from "../utils/feedback";
import { credentialToJSON, isPasskeyAbortError, isPasskeySupported, normalizeCreationOptions } from "../utils/webauthn";

const { useBreakpoint } = Grid;

type ProfileFormValues = {
  nickname?: string;
};

type PasswordFormValues = {
  current_password: string;
  new_password: string;
  confirm_password: string;
};

function OnAuthIcon({ size = 18 }: { size?: number }) {
  return <img src="/onauth.ico" alt="" aria-hidden="true" style={{ width: size, height: size, objectFit: "contain" }} />;
}

export default function ProfilePage() {
  const { user, refreshUser } = useAuth();
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const [profileForm] = Form.useForm<ProfileFormValues>();
  const [passwordForm] = Form.useForm<PasswordFormValues>();
  const [profileSaving, setProfileSaving] = useState(false);
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [onauthEnabled, setOnauthEnabled] = useState(false);
  const [onauthLoading, setOnauthLoading] = useState(false);
  const [passkeys, setPasskeys] = useState<Awaited<ReturnType<typeof fetchPasskeys>>["items"]>([]);
  const [passkeyLoading, setPasskeyLoading] = useState(false);
  const passkeySupported = isPasskeySupported();

  useEffect(() => {
    profileForm.setFieldsValue({ nickname: user?.nickname || "" });
  }, [profileForm, user?.nickname]);

  useEffect(() => {
    fetchOnAuthConfig()
      .then((config) => setOnauthEnabled(config.enabled))
      .catch(() => setOnauthEnabled(false));
  }, []);

  useEffect(() => {
    if (!passkeySupported) {
      return;
    }
    fetchPasskeys()
      .then((result) => setPasskeys(result.items || []))
      .catch(() => setPasskeys([]));
  }, [passkeySupported]);

  const submitProfile = async () => {
    try {
      const values = await profileForm.validateFields();
      setProfileSaving(true);
      notifyActionLoading("profile-save", "保存个人资料中...");
      const result = await updateMyProfile(values);
      await refreshUser();
      notifyActionSuccess("profile-save", result.message || "个人资料已更新");
    } catch (error: any) {
      if (error?.errorFields) {
        notifyActionWarning("profile-save", "请先完善个人资料表单");
        return;
      }
      notifyActionError("profile-save", extractErrorMessage(error, "保存个人资料失败"));
    } finally {
      setProfileSaving(false);
    }
  };

  const submitPassword = async () => {
    try {
      const values = await passwordForm.validateFields();
      setPasswordSaving(true);
      notifyActionLoading("profile-password", "更新密码中...");
      const result = await changeMyPassword({
        current_password: values.current_password,
        new_password: values.new_password,
      });
      passwordForm.resetFields();
      notifyActionSuccess("profile-password", result.message || "密码已更新");
    } catch (error: any) {
      if (error?.errorFields) {
        notifyActionWarning("profile-password", "请先完成密码表单");
        return;
      }
      notifyActionError("profile-password", extractErrorMessage(error, "更新密码失败"));
    } finally {
      setPasswordSaving(false);
    }
  };

  const bindOnAuth = async () => {
    try {
      setOnauthLoading(true);
      const redirectUri = `${window.location.origin}/onauth/callback`;
      const result = await startOnAuth("bind", redirectUri);
      window.location.href = result.authorize_url;
    } catch (error: any) {
      notifyActionError("profile-onauth-bind", extractErrorMessage(error, "启动 OnAuth 绑定失败"));
      setOnauthLoading(false);
    }
  };

  const removeOnAuthBinding = async () => {
    try {
      setOnauthLoading(true);
      const result = await unbindOnAuth();
      await refreshUser();
      notifyActionSuccess("profile-onauth-unbind", result.message || "OnAuth 已解绑");
    } catch (error: any) {
      notifyActionError("profile-onauth-unbind", extractErrorMessage(error, "解绑 OnAuth 失败"));
    } finally {
      setOnauthLoading(false);
    }
  };

  const refreshPasskeys = async () => {
    try {
      const result = await fetchPasskeys();
      setPasskeys(result.items || []);
    } catch {
      setPasskeys([]);
    }
  };

  const bindPasskey = async () => {
    if (!passkeySupported) {
      notifyActionError("profile-passkey", "当前浏览器不支持 Passkey");
      return;
    }
    try {
      setPasskeyLoading(true);
      const origin = window.location.origin;
      const result = await startPasskeyRegistration(origin);
      const credential = await navigator.credentials.create({ publicKey: normalizeCreationOptions(result.options) });
      if (!credential) {
        throw new Error("未获取到 Passkey 凭证");
      }
      const label = `${user?.nickname || user?.username || "Passkey"}-${new Date().toLocaleDateString("zh-CN")}`;
      const verified = await finishPasskeyRegistration({
        challenge_id: result.challenge_id,
        origin,
        credential: credentialToJSON(credential),
        label,
      });
      await refreshPasskeys();
      notifyActionSuccess("profile-passkey", verified.message || "Passkey 已绑定");
    } catch (error: any) {
      if (isPasskeyAbortError(error)) {
        notifyActionWarning("profile-passkey", "Passkey 绑定失败或已主动取消");
        return;
      }
      notifyActionError("profile-passkey", extractErrorMessage(error, "绑定 Passkey 失败"));
    } finally {
      setPasskeyLoading(false);
    }
  };

  const removePasskey = async (credentialId: number) => {
    try {
      setPasskeyLoading(true);
      const result = await deletePasskey(credentialId);
      await refreshPasskeys();
      notifyActionSuccess("profile-passkey-delete", result.message || "Passkey 已删除");
    } catch (error: any) {
      notifyActionError("profile-passkey-delete", extractErrorMessage(error, "删除 Passkey 失败"));
    } finally {
      setPasskeyLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 1080, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <Typography.Title level={isMobile ? 4 : 3} style={{ marginBottom: 6, fontWeight: 700 }}>
          个人中心
        </Typography.Title>
        <Typography.Paragraph style={{ marginBottom: 0, color: "var(--text-sub)" }}>
          维护当前账号资料、安全设置和 OnAuth 绑定状态。
        </Typography.Paragraph>
      </div>

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={11}>
          <Card bordered={false} style={{ borderRadius: 18, background: "var(--glass-bg)", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-main)", height: "100%" }}>
            <Space direction="vertical" size={14} style={{ width: "100%" }}>
              <div>
                <Tag color="processing" style={{ borderRadius: 999 }}>Profile</Tag>
                <Typography.Title level={4} style={{ margin: "12px 0 4px 0" }}>基本资料</Typography.Title>
                <Typography.Text type="secondary">昵称会作为你的展示名，并同步到你名下客户的经理显示名称。</Typography.Text>
              </div>

              <Card size="small" style={{ borderRadius: 16, background: "var(--surface-soft)", borderColor: "var(--glass-border)" }}>
                <Space align="start" size={14}>
                  <div style={{ width: 46, height: 46, borderRadius: "50%", background: "var(--apple-blue)", color: "#fff", display: "grid", placeItems: "center", fontWeight: 700, fontSize: 18 }}>
                    {(user?.nickname || user?.username || "U").slice(0, 1).toUpperCase()}
                  </div>
                  <div>
                    <Typography.Text strong style={{ display: "block", fontSize: 16 }}>{user?.nickname || user?.username || "--"}</Typography.Text>
                    <Typography.Text type="secondary" style={{ display: "block" }}>账号：{user?.username || "--"}</Typography.Text>
                    <Space size={6} wrap style={{ marginTop: 8 }}>
                      <Tag color={user?.role === "admin" ? "purple" : "blue"}>{user?.role === "admin" ? "管理员" : "普通用户"}</Tag>
                      <Tag color={user?.onauth_bound ? "success" : "default"}>{user?.onauth_bound ? "已绑定 OnAuth" : "未绑定 OnAuth"}</Tag>
                    </Space>
                  </div>
                </Space>
              </Card>

              <Divider style={{ margin: "6px 0" }} />

              <Form form={profileForm} layout="vertical">
                <Form.Item label="用户名">
                  <Input value={user?.username || ""} disabled prefix={<UserOutlined />} />
                </Form.Item>
                <Form.Item name="nickname" label="昵称">
                  <Input placeholder="留空则默认显示用户名" maxLength={40} />
                </Form.Item>
                <Button type="primary" icon={<SaveOutlined />} onClick={submitProfile} loading={profileSaving}>保存个人资料</Button>
              </Form>
            </Space>
          </Card>
        </Col>

        <Col xs={24} xl={13}>
          <Card bordered={false} style={{ borderRadius: 18, background: "var(--glass-bg)", border: "1px solid var(--glass-border)", boxShadow: "var(--shadow-main)", height: "100%" }}>
            <Space direction="vertical" size={14} style={{ width: "100%" }}>
              <div>
                <Tag color="warning" style={{ borderRadius: 999 }}>Security</Tag>
                <Typography.Title level={4} style={{ margin: "12px 0 4px 0" }}>密码安全</Typography.Title>
                <Typography.Text type="secondary">修改密码时需要先输入当前密码，避免他人借用登录态直接篡改账号。</Typography.Text>
              </div>

              <Form form={passwordForm} layout="vertical">
                <Form.Item name="current_password" label="当前密码" rules={[{ required: true, message: "请输入当前密码" }]}>
                  <Input.Password prefix={<KeyOutlined />} placeholder="请输入当前密码" />
                </Form.Item>
                <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: "请输入新密码" }, { min: 6, message: "新密码至少 6 位" }]}>
                  <Input.Password placeholder="请输入新密码" />
                </Form.Item>
                <Form.Item
                  name="confirm_password"
                  label="确认新密码"
                  dependencies={["new_password"]}
                  rules={[
                    { required: true, message: "请再次输入新密码" },
                    ({ getFieldValue }) => ({
                      validator(_, value) {
                        if (!value || getFieldValue("new_password") === value) return Promise.resolve();
                        return Promise.reject(new Error("两次输入的新密码不一致"));
                      },
                    }),
                  ]}
                >
                  <Input.Password placeholder="请再次输入新密码" />
                </Form.Item>
                <Button type="primary" icon={<SaveOutlined />} onClick={submitPassword} loading={passwordSaving}>更新登录密码</Button>
              </Form>

              <Divider />

              <div>
                <Tag color={user?.onauth_bound ? "success" : "default"} style={{ borderRadius: 999 }}>
                  <Space size={5}><OnAuthIcon size={14} />OnAuth</Space>
                </Tag>
                <Typography.Title level={4} style={{ margin: "12px 0 4px 0" }}>OnAuth 绑定</Typography.Title>
                <Typography.Text type="secondary">绑定后可在登录页直接使用 OnAuth 登录当前 SubSentry 账号。</Typography.Text>
                <Card size="small" style={{ marginTop: 12, borderRadius: 14, background: "var(--surface-soft)", borderColor: "var(--glass-border)" }}>
                  <Space direction="vertical" size={10} style={{ width: "100%" }}>
                    <Typography.Text>当前状态：<Typography.Text strong>{user?.onauth_bound ? "已绑定" : "未绑定"}</Typography.Text></Typography.Text>
                    {user?.onauth_bound ? (
                      <Typography.Text type="secondary">
                        OnAuth 账号：{user.onauth_username || "未返回账号名"}{user.onauth_bound_at ? ` / 绑定时间：${user.onauth_bound_at}` : ""}
                      </Typography.Text>
                    ) : null}
                    {onauthEnabled ? (
                      user?.onauth_bound ? (
                        <Popconfirm title="确认解绑 OnAuth？" onConfirm={() => void removeOnAuthBinding()} okText="解绑" cancelText="取消">
                          <Button danger icon={<LinkOutlined />} loading={onauthLoading}>解绑 OnAuth</Button>
                        </Popconfirm>
                      ) : (
                        <Button icon={<LoginOutlined />} loading={onauthLoading} onClick={() => void bindOnAuth()}>
                          <Space size={6}><OnAuthIcon />绑定 OnAuth</Space>
                        </Button>
                      )
                    ) : (
                      <Typography.Text type="secondary">OnAuth 尚未配置，请管理员先配置服务端环境变量。</Typography.Text>
                    )}
                  </Space>
                </Card>
              </div>

              <Divider />

              <div>
                <Tag color="purple" style={{ borderRadius: 999 }}>Passkey</Tag>
                <Typography.Title level={4} style={{ margin: "12px 0 4px 0" }}>Passkey 登录</Typography.Title>
                <Typography.Text type="secondary">使用系统级安全密钥、指纹或人脸登录当前账号。</Typography.Text>
                <Card size="small" style={{ marginTop: 12, borderRadius: 14, background: "var(--surface-soft)", borderColor: "var(--glass-border)" }}>
                  <Space direction="vertical" size={10} style={{ width: "100%" }}>
                    <Space wrap>
                      <Button type="primary" loading={passkeyLoading} onClick={() => void bindPasskey()} disabled={!passkeySupported}>添加 Passkey</Button>
                      <Typography.Text type="secondary">{passkeySupported ? "已支持" : "当前浏览器不支持"}</Typography.Text>
                    </Space>
                    <List
                      size="small"
                      dataSource={passkeys}
                      locale={{ emptyText: "暂无已绑定 Passkey" }}
                      renderItem={(item) => (
                        <List.Item
                          actions={[
                            <Popconfirm key="delete" title="确认删除这个 Passkey？" onConfirm={() => void removePasskey(item.id)} okText="删除" cancelText="取消">
                              <Button danger size="small">删除</Button>
                            </Popconfirm>,
                          ]}
                        >
                          <List.Item.Meta
                            title={item.label}
                            description={`${item.device_type} · 创建于 ${item.created_at}${item.last_used_at ? ` · 最近使用 ${item.last_used_at}` : ""}`}
                          />
                        </List.Item>
                      )}
                    />
                  </Space>
                </Card>
              </div>
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
