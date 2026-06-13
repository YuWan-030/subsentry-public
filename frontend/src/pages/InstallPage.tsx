import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Form, Input, InputNumber, Radio, Space, Steps, Typography } from "antd";
import { CheckCircleOutlined, DatabaseOutlined, GlobalOutlined, KeyOutlined, ReloadOutlined } from "@ant-design/icons";
import { completeInstall, fetchInstallStatus, saveInstallDatabase, testInstallDatabase, type InstallDatabasePayload, type InstallStatus } from "../api/install";
import { CuteBrandIcon, CuteStickerCluster } from "../components/CuteDecor";
import SiteFooter from "../components/SiteFooter";
import { extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess } from "../utils/feedback";

type DatabaseFormValues = InstallDatabasePayload;

type CompleteFormValues = {
  admin_username: string;
  admin_password: string;
  admin_password_confirm: string;
  admin_nickname?: string;
  site_url?: string;
  webhook_url?: string;
};

const ADMIN_FIELDS: Array<keyof CompleteFormValues> = ["admin_username", "admin_password", "admin_password_confirm", "admin_nickname"];
const SITE_FIELDS: Array<keyof CompleteFormValues> = ["site_url", "webhook_url"];

export default function InstallPage({ onFinished }: { onFinished: () => Promise<void> }) {
  const [status, setStatus] = useState<InstallStatus | null>(null);
  const [current, setCurrent] = useState(0);
  const [loading, setLoading] = useState(false);
  const [restartRequired, setRestartRequired] = useState(false);
  const [databaseForm] = Form.useForm<DatabaseFormValues>();
  const [completeForm] = Form.useForm<CompleteFormValues>();
  const dbType = Form.useWatch("db_type", databaseForm) || "sqlite";

  const initialSiteUrl = useMemo(() => {
    if (status?.site_url) {
      return status.site_url;
    }
    return window.location.origin;
  }, [status]);

  const loadStatus = async () => {
    try {
      const data = await fetchInstallStatus();
      setStatus(data);
      databaseForm.setFieldsValue({
        db_type: data.database.type || "sqlite",
        sqlite_file: data.database.sqlite_file || "subsentry.db",
        mysql_host: data.database.mysql?.host || "127.0.0.1",
        mysql_port: data.database.mysql?.port || 3306,
        mysql_user: data.database.mysql?.user || "subsentry",
        mysql_database: data.database.mysql?.database || "subsentry",
      });
      completeForm.setFieldsValue({ site_url: data.site_url || window.location.origin });
    } catch (error: any) {
      notifyActionError("install-status", extractErrorMessage(error, "加载安装状态失败"));
    }
  };

  useEffect(() => {
    void loadStatus();
  }, []);

  useEffect(() => {
    completeForm.setFieldValue("site_url", initialSiteUrl);
  }, [completeForm, initialSiteUrl]);

  const testDatabase = async () => {
    const values = await databaseForm.validateFields();
    try {
      setLoading(true);
      notifyActionLoading("install-db-test", "正在检测数据库连接...");
      const result = await testInstallDatabase(values);
      notifyActionSuccess("install-db-test", result.message || "数据库连接正常");
    } catch (error: any) {
      notifyActionError("install-db-test", extractErrorMessage(error, "数据库连接失败"));
    } finally {
      setLoading(false);
    }
  };

  const saveDatabase = async () => {
    const values = await databaseForm.validateFields();
    try {
      setLoading(true);
      notifyActionLoading("install-db-save", "正在保存数据库配置...");
      const result = await saveInstallDatabase(values);
      setRestartRequired(Boolean(result.restart_required));
      notifyActionSuccess("install-db-save", result.message || "数据库配置已保存");
      if (!result.restart_required) {
        setCurrent(1);
      }
    } catch (error: any) {
      notifyActionError("install-db-save", extractErrorMessage(error, "保存数据库配置失败"));
    } finally {
      setLoading(false);
    }
  };

  const goSiteStep = async () => {
    const values = await completeForm.validateFields(ADMIN_FIELDS);
    if (values.admin_password !== values.admin_password_confirm) {
      completeForm.setFields([{ name: "admin_password_confirm", errors: ["两次输入的密码不一致"] }]);
      return;
    }
    setCurrent(2);
  };

  const finishInstall = async () => {
    const values = await completeForm.validateFields([...ADMIN_FIELDS, ...SITE_FIELDS]);
    if (values.admin_password !== values.admin_password_confirm) {
      completeForm.setFields([{ name: "admin_password_confirm", errors: ["两次输入的密码不一致"] }]);
      setCurrent(1);
      return;
    }
    try {
      setLoading(true);
      notifyActionLoading("install-complete", "正在完成安装...");
      await completeInstall({
        admin_username: values.admin_username,
        admin_password: values.admin_password,
        admin_nickname: values.admin_nickname,
        site_url: values.site_url,
        webhook_url: values.webhook_url,
      });
      notifyActionSuccess("install-complete", "安装完成");
      await onFinished();
    } catch (error: any) {
      notifyActionError("install-complete", extractErrorMessage(error, "安装失败"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="install-shell">
      <CuteStickerCluster />
      <Card className="install-card" bordered={false}>
        <Space direction="vertical" size={22} style={{ width: "100%" }}>
          <div className="install-brand-row">
            <CuteBrandIcon size={46} />
            <div>
              <Typography.Title level={2} style={{ margin: 0 }}>
                SubSentry 安装向导
              </Typography.Title>
              <Typography.Text type="secondary">按步骤完成数据库、管理员和站点通知配置</Typography.Text>
            </div>
          </div>

          <Steps
            current={current}
            items={[
              { title: "数据库", description: "选择存储方式", icon: <DatabaseOutlined /> },
              { title: "管理员", description: "创建首个账号", icon: <KeyOutlined /> },
              { title: "站点与通知", description: "公开地址和 Webhook", icon: <GlobalOutlined /> },
            ]}
          />

          {current === 0 ? (
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
              <Alert
                type="info"
                showIcon
                message="先选择数据存储方式"
                description="SQLite 适合轻量单机部署；MySQL 适合公网服务器、多人使用和长期运行。数据库配置会写入项目根目录 .env。"
              />
              {restartRequired ? (
                <Alert
                  type="warning"
                  showIcon
                  message="数据库配置已保存，需要重启后端"
                  description="重启后端后刷新本页，系统会使用新的数据库配置并继续安装流程。"
                  action={<Button icon={<ReloadOutlined />} onClick={() => window.location.reload()}>刷新</Button>}
                />
              ) : null}
              <Form
                form={databaseForm}
                layout="vertical"
                initialValues={{ db_type: "sqlite", sqlite_file: "subsentry.db", mysql_host: "127.0.0.1", mysql_port: 3306, mysql_user: "subsentry", mysql_database: "subsentry" }}
              >
                <Form.Item name="db_type" label="数据库类型" rules={[{ required: true }]}>
                  <Radio.Group optionType="button" buttonStyle="solid">
                    <Radio.Button value="sqlite">SQLite</Radio.Button>
                    <Radio.Button value="mysql">MySQL</Radio.Button>
                  </Radio.Group>
                </Form.Item>

                {dbType === "sqlite" ? (
                  <>
                    <Alert
                      type="success"
                      showIcon
                      message="SQLite 模式"
                      description="默认会在项目目录中创建数据库文件，适合快速开始。生产环境请定期备份该文件。"
                      style={{ marginBottom: 16 }}
                    />
                    <Form.Item name="sqlite_file" label="SQLite 文件路径" rules={[{ required: true, message: "请输入 SQLite 文件路径" }]}>
                      <Input placeholder="subsentry.db" />
                    </Form.Item>
                  </>
                ) : (
                  <>
                    <Alert
                      type="warning"
                      showIcon
                      message="MySQL 模式"
                      description="请先创建数据库，并确保账号有建表、读写和修改表结构权限。保存后通常需要重启后端才能切换到 MySQL。"
                      style={{ marginBottom: 16 }}
                    />
                    <div className="install-grid">
                      <Form.Item name="mysql_host" label="MySQL 地址" rules={[{ required: true, message: "请输入 MySQL 地址" }]}>
                        <Input placeholder="127.0.0.1 或 mysql.example.com" />
                      </Form.Item>
                      <Form.Item name="mysql_port" label="MySQL 端口" rules={[{ required: true, message: "请输入 MySQL 端口" }]}>
                        <InputNumber min={1} max={65535} style={{ width: "100%" }} placeholder="3306" />
                      </Form.Item>
                      <Form.Item name="mysql_user" label="MySQL 用户名" rules={[{ required: true, message: "请输入 MySQL 用户名" }]}>
                        <Input placeholder="subsentry" autoComplete="username" />
                      </Form.Item>
                      <Form.Item name="mysql_password" label="MySQL 密码" rules={[{ required: true, message: "请输入 MySQL 密码" }]}>
                        <Input.Password placeholder="数据库密码" autoComplete="new-password" />
                      </Form.Item>
                      <Form.Item name="mysql_database" label="数据库名" rules={[{ required: true, message: "请输入数据库名" }]}>
                        <Input placeholder="subsentry" />
                      </Form.Item>
                    </div>
                  </>
                )}
              </Form>
              <Space wrap>
                <Button onClick={() => void testDatabase()} loading={loading}>
                  测试连接
                </Button>
                <Button type="primary" onClick={() => void saveDatabase()} loading={loading} disabled={restartRequired}>
                  保存数据库配置
                </Button>
                <Button onClick={() => setCurrent(1)} disabled={restartRequired}>
                  使用当前配置继续
                </Button>
              </Space>
            </Space>
          ) : null}

          <Form form={completeForm} layout="vertical" hidden={current === 0}>
            {current === 1 ? (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
                <Alert
                  type="info"
                  showIcon
                  message="创建第一个管理员"
                  description="该账号拥有系统全部管理权限。请设置一个足够强的密码，安装完成后会自动登录。"
                />
                <div className="install-grid">
                  <Form.Item name="admin_username" label="管理员账号" rules={[{ required: true, message: "请输入管理员账号" }]}>
                    <Input placeholder="admin" autoComplete="username" />
                  </Form.Item>
                  <Form.Item name="admin_nickname" label="显示昵称">
                    <Input placeholder="管理员" />
                  </Form.Item>
                  <Form.Item name="admin_password" label="管理员密码" rules={[{ required: true, min: 8, message: "密码至少 8 位" }]}>
                    <Input.Password placeholder="至少 8 位" autoComplete="new-password" />
                  </Form.Item>
                  <Form.Item name="admin_password_confirm" label="确认密码" rules={[{ required: true, message: "请再次输入密码" }]}>
                    <Input.Password placeholder="再次输入密码" autoComplete="new-password" />
                  </Form.Item>
                </div>
                <Space wrap>
                  <Button onClick={() => setCurrent(0)}>返回数据库配置</Button>
                  <Button type="primary" onClick={() => void goSiteStep()}>
                    下一步
                  </Button>
                </Space>
              </Space>
            ) : null}

            {current === 2 ? (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
                <Alert
                  type="success"
                  showIcon
                  icon={<CheckCircleOutlined />}
                  message="最后一步：站点与通知"
                  description="站点 URL 会用于生成公开订阅地址。Webhook 可留空，后续也可以在系统设置或客户资料中补充。"
                />
                <div className="install-grid">
                  <Form.Item name="site_url" label="站点 URL" rules={[{ required: true, message: "请输入站点 URL" }]}>
                    <Input placeholder="https://example.com" />
                  </Form.Item>
                  <Form.Item name="webhook_url" label="默认 Webhook">
                    <Input placeholder="企业微信 / 飞书 / 自定义 Webhook URL" />
                  </Form.Item>
                </div>
                <Space wrap>
                  <Button onClick={() => setCurrent(1)}>返回管理员配置</Button>
                  <Button type="primary" onClick={() => void finishInstall()} loading={loading}>
                    完成安装
                  </Button>
                </Space>
              </Space>
            ) : null}
          </Form>
        </Space>
      </Card>
      <SiteFooter fixed />
    </div>
  );
}
