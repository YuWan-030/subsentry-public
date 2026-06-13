import { useEffect, useState } from "react";
import { Button, Card, Col, Checkbox, Form, Grid, Input, InputNumber, Row, Select, Space, Tag, Typography } from "antd";
import { SaveOutlined, SettingOutlined, UserOutlined, ClusterOutlined, SyncOutlined, NotificationOutlined, GlobalOutlined } from "@ant-design/icons";
import { fetchAdminSiteConfig, fetchLocalSubscriptionConfig, saveLocalSubscriptionConfig, saveNotificationConfig, saveNotificationTemplate, saveSiteConfig } from "../api/settings";
import type { LocalSubscriptionConfig, SiteConfig } from "../api/settings";
import api from "../api/http";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../api/auth";
import { extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess, notifyDataLoaded } from "../utils/feedback";

const { useBreakpoint } = Grid;

// 定义推送策略的表单类型
type ConfigFormValues = {
  push_mode: string;
  max_detail_rows: number;
  fixed_push_time: string;
  fixed_push_time_enabled: boolean;
  push_time_window_minutes: number;
};

type TemplateFormValues = {
  notification_template: string;
  notification_template_traffic_low?: string;
  notification_template_customer_disabled?: string;
  notification_template_node_abnormal?: string;
  notification_template_summary?: string;
};

type TemplatePresets = Required<TemplateFormValues>;

type SiteFormValues = SiteConfig;
type LocalSubscriptionFormValues = LocalSubscriptionConfig;

const DEFAULT_CONFIG_VALUES: ConfigFormValues = {
  push_mode: "summary",
  max_detail_rows: 30,
  fixed_push_time: "09:00",
  fixed_push_time_enabled: false,
  push_time_window_minutes: 20,
};

export default function SettingsPage() {
  const { user } = useAuth();
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const navigate = useNavigate();
  const [optionsLoading, setOptionsLoading] = useState(false);
  const [templateSaving, setTemplateSaving] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [siteSaving, setSiteSaving] = useState(false);
  const [localSubscriptionSaving, setLocalSubscriptionSaving] = useState(false);
  const [checkSubmitting, setCheckSubmitting] = useState(false);
  const [templatePresets, setTemplatePresets] = useState<TemplatePresets | null>(null);
  const [templateForm] = Form.useForm<TemplateFormValues>();
  const [configForm] = Form.useForm<ConfigFormValues>();
  const [siteForm] = Form.useForm<SiteFormValues>();
  const [localSubscriptionForm] = Form.useForm<LocalSubscriptionFormValues>();
  const [pushModes] = useState([
    { value: "summary", label: "汇总推送" },
    { value: "manager_summary", label: "按客户经理汇总" },
    { value: "per_customer", label: "逐客户推送" },
    { value: "hybrid", label: "混合模式" },
  ]);

  // 全局卡片统一样式，打造微阴影轻量感
  const cardStyle = {
    borderRadius: 16,
    boxShadow: "var(--shadow-main)",
    border: "1px solid var(--glass-border)",
    background: "var(--glass-bg)",
    height: "100%", // 保持两侧卡片等高
  };

  const loadData = async (showSuccess = false) => {
    setOptionsLoading(true);
    try {
      configForm.setFieldsValue(DEFAULT_CONFIG_VALUES);
      // 同时获取模板和配置数据
      const [templateRes, configRes, siteRes, localSubscriptionRes] = await Promise.all([
        api.get("/api/v1/settings/notification-template"),
        api.get("/api/v1/settings/notification-config").catch(() => ({ data: DEFAULT_CONFIG_VALUES })),
        fetchAdminSiteConfig().catch(() => null),
        fetchLocalSubscriptionConfig().catch(() => null),
      ]);

      if (templateRes.data) {
        templateForm.setFieldsValue({
          notification_template: templateRes.data.notification_template,
          notification_template_traffic_low: templateRes.data.notification_template_traffic_low,
          notification_template_customer_disabled: templateRes.data.notification_template_customer_disabled,
          notification_template_node_abnormal: templateRes.data.notification_template_node_abnormal,
          notification_template_summary: templateRes.data.notification_template_summary,
        });
        setTemplatePresets(templateRes.data.presets || null);
      }
      if (configRes.data) {
        configForm.setFieldsValue(configRes.data);
      }
      siteForm.setFieldsValue(
        siteRes || {
          announcement_enabled: false,
          announcement_text: "",
          icp_number: "",
          icp_link: "",
        },
      );
      localSubscriptionForm.setFieldsValue(
        localSubscriptionRes || {
          enabled: false,
          base_url: "http://127.0.0.1:10883",
          port: 10883,
          title: "SubSentry",
        },
      );
      if (showSuccess) {
        notifyDataLoaded("settings-load", "系统设置已刷新");
      }
    } catch (error: any) {
      notifyActionError("settings-load", extractErrorMessage(error, "加载设置失败"));
    } finally {
      setOptionsLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const submitTemplate = async () => {
    try {
      const values = await templateForm.validateFields();
      setTemplateSaving(true);
      notifyActionLoading("settings-template-save", "保存通知模板中...");
      const result = await saveNotificationTemplate(values);
      notifyActionSuccess("settings-template-save", result.message || "模板保存成功");
    } catch (error: any) {
      if (error?.errorFields) return; // 表单自带校验提示，无需弹窗
      notifyActionError("settings-template-save", extractErrorMessage(error, "保存失败"));
    } finally {
      setTemplateSaving(false);
    }
  };

  const submitConfig = async () => {
    try {
      const values = await configForm.validateFields();
      setConfigSaving(true);
      notifyActionLoading("settings-config-save", "保存推送策略中...");
      const result = await saveNotificationConfig(values);
      notifyActionSuccess("settings-config-save", result.message || "策略保存成功");
    } catch (error: any) {
      if (error?.errorFields) return;
      notifyActionError("settings-config-save", extractErrorMessage(error, "保存失败"));
    } finally {
      setConfigSaving(false);
    }
  };

  const submitSiteConfig = async () => {
    try {
      const values = await siteForm.validateFields();
      setSiteSaving(true);
      notifyActionLoading("settings-site-save", "保存站点展示设置中...");
      const result = await saveSiteConfig({
        announcement_enabled: Boolean(values.announcement_enabled),
        announcement_text: values.announcement_text || "",
        icp_number: values.icp_number || "",
        icp_link: values.icp_link || "",
      });
      notifyActionSuccess("settings-site-save", result.message || "站点展示设置已保存");
    } catch (error: any) {
      if (error?.errorFields) return;
      notifyActionError("settings-site-save", extractErrorMessage(error, "保存失败"));
    } finally {
      setSiteSaving(false);
    }
  };

  const submitLocalSubscriptionConfig = async () => {
    try {
      const values = await localSubscriptionForm.validateFields();
      setLocalSubscriptionSaving(true);
      notifyActionLoading("settings-local-subscription-save", "保存本地订阅设置中...");
      const result = await saveLocalSubscriptionConfig({
        enabled: Boolean(values.enabled),
        base_url: (values.base_url || "").trim(),
        port: Number(values.port || 10883),
        title: (values.title || "SubSentry").trim(),
      });
      localSubscriptionForm.setFieldsValue(result.data);
      notifyActionSuccess("settings-local-subscription-save", result.message || "本地订阅设置已保存");
    } catch (error: any) {
      if (error?.errorFields) return;
      notifyActionError("settings-local-subscription-save", extractErrorMessage(error, "保存失败"));
    } finally {
      setLocalSubscriptionSaving(false);
    }
  };

  const triggerWebhookCheck = async () => {
    try {
      setCheckSubmitting(true);
      notifyActionLoading("settings-webhook-check", "正在执行推送检查...");
      const response = await api.post("/api/v1/cron/check");
      const data = response.data || {};
      const message = `触发 ${data.triggered || 0} 条，跳过 ${data.skipped || 0} 条${Array.isArray(data.errors) && data.errors.length ? `，失败 ${data.errors.length} 条` : ""}`;
      notifyActionSuccess("settings-webhook-check", message);
    } catch (error: any) {
      notifyActionError("settings-webhook-check", extractErrorMessage(error, "执行推送检查失败"));
    } finally {
      setCheckSubmitting(false);
    }
  };

  const applyPreset = (field?: keyof TemplateFormValues) => {
    if (!templatePresets) {
      return;
    }
    if (field) {
      templateForm.setFieldValue(field, templatePresets[field]);
      return;
    }
    templateForm.setFieldsValue(templatePresets);
  };

  if (user?.role !== "admin") {
    return (
      <Card style={{ borderRadius: 16, textAlign: "center", padding: "40px 20px" }}>
        <Typography.Title level={4} type="danger">权限受限</Typography.Title>
        <Typography.Paragraph type="secondary">当前账号无权访问系统设置，仅管理员可见。</Typography.Paragraph>
      </Card>
    );
  }

  return (
    <div style={{ padding: isMobile ? "0" : "12px 0", maxWidth: 1400, margin: "0 auto" }}>
      {/* 头部标题区 */}
      <div style={{ marginBottom: 24, borderBottom: "1px solid var(--glass-border)", paddingBottom: 16 }}>
        <Space align="center" size={12}>
          <div style={{ background: "var(--surface-soft)", padding: 8, borderRadius: 10, display: "flex" }}>
            <SettingOutlined style={{ fontSize: 22, color: "var(--apple-blue)" }} />
          </div>
          <div>
            <Typography.Title level={isMobile ? 4 : 3} style={{ margin: 0, fontWeight: 600, color: "var(--text-main)" }}>
              系统设置
            </Typography.Title>
            <Typography.Text style={{ color: "var(--text-sub)", fontSize: 13 }}>
              集中管理全局通知模板、推送策略调度及核心集群目录。
            </Typography.Text>
          </div>
        </Space>
      </div>

      {/* 主内容区 */}
      <Row gutter={[20, 20]} style={{ alignItems: "stretch" }}>
        {/* 左侧：通知模板 */}
        <Col xs={24} xl={11}>
          <Card loading={optionsLoading} bordered={false} style={cardStyle} bodyStyle={{ padding: isMobile ? 14 : 24 }}>
            <div style={{ marginBottom: 16 }}>
              <Tag color="processing" style={{ borderRadius: 6, padding: "2px 8px" }}>Notification</Tag>
              <Typography.Title level={4} style={{ marginTop: 12, marginBottom: 4, fontWeight: 600 }}>
                通知模板
              </Typography.Title>
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                支持企业微信 Markdown，颜色建议使用 info、warning、comment。
              </Typography.Text>
            </div>

            <Form form={templateForm} layout="vertical">
              <Space wrap style={{ marginBottom: 16, width: "100%" }}>
                <Button onClick={() => applyPreset()} disabled={!templatePresets}>套用全部预设</Button>
                <Button onClick={() => applyPreset("notification_template")} disabled={!templatePresets}>到期预设</Button>
                <Button onClick={() => applyPreset("notification_template_traffic_low")} disabled={!templatePresets}>流量预设</Button>
                <Button onClick={() => applyPreset("notification_template_customer_disabled")} disabled={!templatePresets}>停用预设</Button>
                <Button onClick={() => applyPreset("notification_template_node_abnormal")} disabled={!templatePresets}>节点预设</Button>
                <Button onClick={() => applyPreset("notification_template_summary")} disabled={!templatePresets}>汇总预设</Button>
              </Space>
              <Form.Item
                name="notification_template"
                label={<span style={{ fontWeight: 500, color: "#475569" }}>到期提醒模板</span>}
                rules={[{ required: true, message: "请输入模板内容" }]}
              >
                <Input.TextArea
                  placeholder="支持变量：{name} {manager} {node} {price} {expiry} {rem} {status} {time}"
                  autoSize={{ minRows: 7, maxRows: 12 }}
                  style={{ borderRadius: 8, borderColor: "#cbd5e1" }}
                />
              </Form.Item>
              <Form.Item name="notification_template_traffic_low" label={<span style={{ fontWeight: 500, color: "#475569" }}>流量不足模板</span>}>
                <Input.TextArea
                  placeholder="留空时复用到期提醒模板"
                  autoSize={{ minRows: 4, maxRows: 8 }}
                  style={{ borderRadius: 8, borderColor: "#cbd5e1" }}
                />
              </Form.Item>
              <Form.Item name="notification_template_customer_disabled" label={<span style={{ fontWeight: 500, color: "#475569" }}>客户停用模板</span>}>
                <Input.TextArea
                  placeholder="留空时复用到期提醒模板"
                  autoSize={{ minRows: 4, maxRows: 8 }}
                  style={{ borderRadius: 8, borderColor: "#cbd5e1" }}
                />
              </Form.Item>
              <Form.Item name="notification_template_node_abnormal" label={<span style={{ fontWeight: 500, color: "#475569" }}>节点异常模板</span>}>
                <Input.TextArea
                  placeholder="支持变量：{node} {status} {time}"
                  autoSize={{ minRows: 4, maxRows: 8 }}
                  style={{ borderRadius: 8, borderColor: "#cbd5e1" }}
                />
              </Form.Item>
              <Form.Item name="notification_template_summary" label={<span style={{ fontWeight: 500, color: "#475569" }}>汇总推送模板</span>}>
                <Input.TextArea
                  placeholder="支持变量：{title} {time} {count} {expired} {due_today} {warning} {traffic_low} {disabled} {detail}"
                  autoSize={{ minRows: 6, maxRows: 12 }}
                  style={{ borderRadius: 8, borderColor: "#cbd5e1" }}
                />
              </Form.Item>
              <Typography.Text type="secondary" style={{ display: "block", marginBottom: 12, fontSize: 12 }}>
                可用客户变量：{"{name} {manager} {node} {price} {expiry} {rem} {status} {traffic} {traffic_total} {traffic_used} {traffic_remaining} {time}"}
              </Typography.Text>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={submitTemplate}
                loading={templateSaving}
                size="large"
                style={{ borderRadius: 8, fontWeight: 500, boxShadow: "var(--shadow-smooth)" }}
              >
                保存模板设置
              </Button>
            </Form>
          </Card>
        </Col>

        {/* 右侧：推送策略 */}
        <Col xs={24} xl={13}>
          <Card loading={optionsLoading} bordered={false} style={cardStyle} bodyStyle={{ padding: isMobile ? 14 : 24 }}>
            <div style={{ marginBottom: 16 }}>
              <Tag color="warning" style={{ borderRadius: 6, padding: "2px 8px" }}>Policy Strategy</Tag>
              <Typography.Title level={4} style={{ marginTop: 12, marginBottom: 4, fontWeight: 600 }}>
                推送策略
              </Typography.Title>
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                由系统统一调度控制汇总、单发或混合推送模式。
              </Typography.Text>
            </div>

            <Form form={configForm} layout="vertical" initialValues={DEFAULT_CONFIG_VALUES}>
              <Row gutter={16}>
                <Col span={24}>
                  <Form.Item name="push_mode" label={<span style={{ fontWeight: 500, color: "#475569" }}>推送模式</span>} rules={[{ required: true, message: "请选择推送模式" }]}>
                    <Select options={pushModes} size="large" style={{ width: "100%" }} dropdownStyle={{ borderRadius: 8 }} />
                  </Form.Item>
                </Col>

                <Col xs={24} sm={12}>
                  <Form.Item name="max_detail_rows" label={<span style={{ fontWeight: 500, color: "#475569" }}>汇总详情最大行数</span>} rules={[{ required: true, message: "请输入最大行数" }]}>
                    <InputNumber min={5} max={200} style={{ width: "100%", borderRadius: 8 }} size="large" />
                  </Form.Item>
                </Col>

                <Col xs={24} sm={12}>
                  <Form.Item
                    name="push_time_window_minutes"
                    label={<span style={{ fontWeight: 500, color: "#475569" }}>时间窗口（分钟）</span>}
                    tooltip="启用固定时间后，计划任务只有在固定时间之后的这段分钟数内才会真正发送。"
                    extra="例如固定 09:00，窗口 20，表示 09:00-09:20 内触发有效。"
                    rules={[{ required: true, message: "请输入时间窗口" }]}
                  >
                    <InputNumber min={1} max={180} style={{ width: "100%", borderRadius: 8 }} size="large" />
                  </Form.Item>
                </Col>

                <Col xs={24} sm={14}>
                  <Form.Item
                    name="fixed_push_time"
                    label={<span style={{ fontWeight: 500, color: "#475569" }}>固定推送时间</span>}
                    extra="关闭固定时间时，只要计划任务调用检查接口，就会按规则推送。"
                    rules={[{ required: true, message: "请输入固定推送时间" }]}
                  >
                    <Input placeholder="例如 09:30" size="large" style={{ borderRadius: 8 }} />
                  </Form.Item>
                </Col>

                <Col xs={24} sm={10} style={{ display: "flex", alignItems: "center" }}>
                  <Form.Item name="fixed_push_time_enabled" valuePropName="checked" style={{ marginBottom: 0, marginTop: 8 }}>
                    <Checkbox><span style={{ color: "#475569", fontWeight: 500 }}>启用固定时间推送</span></Checkbox>
                  </Form.Item>
                </Col>
              </Row>

              <div style={{ marginTop: 20 }}>
                <Space wrap>
                  <Button
                    type="primary"
                    icon={<SaveOutlined />}
                    onClick={submitConfig}
                    loading={configSaving}
                    size="large"
                    style={{ borderRadius: 8, fontWeight: 500, backgroundColor: "var(--status-warning)", borderColor: "var(--status-warning)", boxShadow: "var(--shadow-smooth)" }}
                  >
                    保存策略控制
                  </Button>
                  <Button
                    icon={<SyncOutlined />}
                    onClick={triggerWebhookCheck}
                    loading={checkSubmitting}
                    size="large"
                    style={{ borderRadius: 8 }}
                  >
                    立即检查推送
                  </Button>
                </Space>
              </div>
            </Form>

            <div style={{ marginTop: 28, paddingTop: 22, borderTop: "1px solid var(--glass-border)" }}>
              <Tag color="blue" style={{ borderRadius: 6, padding: "2px 8px" }}>Local Subscription</Tag>
              <Typography.Title level={5} style={{ marginTop: 12, marginBottom: 4, fontWeight: 600 }}>
                本地订阅链接
              </Typography.Title>
              <Typography.Text type="secondary" style={{ display: "block", fontSize: 13, marginBottom: 16 }}>
                开启后客户弹窗只显示 SubSentry 本地生成的订阅链接；关闭后本地订阅接口停用，弹窗回到 3X-UI 原始链接。
              </Typography.Text>

              <Form form={localSubscriptionForm} layout="vertical">
                <Row gutter={16}>
                  <Col xs={24} sm={12} style={{ display: "flex", alignItems: "center" }}>
                    <Form.Item name="enabled" valuePropName="checked" style={{ marginBottom: isMobile ? 12 : 22 }}>
                      <Checkbox><span style={{ color: "#475569", fontWeight: 500 }}>启用本地订阅链接</span></Checkbox>
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="port"
                      label={<span style={{ fontWeight: 500, color: "#475569" }}>监听端口</span>}
                      extra="主程序会自动按此端口监听；修改端口后会自动重启本地订阅监听。"
                      rules={[{ required: true, message: "请输入监听端口" }]}
                    >
                      <InputNumber min={1} max={65535} size="large" style={{ width: "100%", borderRadius: 8 }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="title"
                      label={<span style={{ fontWeight: 500, color: "#475569" }}>订阅 Title</span>}
                      rules={[{ required: true, message: "请输入订阅 Title" }]}
                    >
                      <Input placeholder="SubSentry" size="large" style={{ borderRadius: 8 }} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12}>
                    <Form.Item
                      name="base_url"
                      label={<span style={{ fontWeight: 500, color: "#475569" }}>公开链接</span>}
                      extra="例如 http://你的域名:10883，会生成 /sub、/json、/clash 链接。"
                      rules={[{ required: true, message: "请输入公开链接" }]}
                    >
                      <Input placeholder="http://127.0.0.1:10883" size="large" style={{ borderRadius: 8 }} />
                    </Form.Item>
                  </Col>
                </Row>
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  onClick={submitLocalSubscriptionConfig}
                  loading={localSubscriptionSaving}
                  size="large"
                  style={{ borderRadius: 8, fontWeight: 500, boxShadow: "var(--shadow-smooth)" }}
                >
                  保存本地订阅设置
                </Button>
              </Form>
            </div>
          </Card>
        </Col>
      </Row>

      <Card
        loading={optionsLoading}
        bordered={false}
        style={{ ...cardStyle, marginTop: 20 }}
        bodyStyle={{ padding: isMobile ? 14 : 24 }}
      >
        <div style={{ marginBottom: 16 }}>
          <Tag color="processing" style={{ borderRadius: 6, padding: "2px 8px" }}>Site Display</Tag>
          <Typography.Title level={4} style={{ marginTop: 12, marginBottom: 4, fontWeight: 600 }}>
            站点展示
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            配置资产总览顶部公告，以及网页底部备案号展示。
          </Typography.Text>
        </div>

        <Form form={siteForm} layout="vertical">
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="announcement_enabled" valuePropName="checked" style={{ marginBottom: isMobile ? 12 : 0 }}>
                <Checkbox>
                  <Space size={6}>
                    <NotificationOutlined style={{ color: "var(--apple-blue)" }} />
                    <span style={{ color: "#475569", fontWeight: 500 }}>启用首页公告</span>
                  </Space>
                </Checkbox>
              </Form.Item>
            </Col>
            <Col xs={24} md={16}>
              <Form.Item name="announcement_text" label={<span style={{ fontWeight: 500, color: "#475569" }}>公告内容</span>}>
                <Input.TextArea
                  placeholder="例如：系统将于今晚 23:00 进行维护，请提前关注客户到期与节点状态。"
                  autoSize={{ minRows: 2, maxRows: 4 }}
                  maxLength={300}
                  showCount
                  style={{ borderRadius: 8, borderColor: "#cbd5e1" }}
                />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="icp_number" label={<span style={{ fontWeight: 500, color: "#475569" }}>备案号</span>}>
                <Input prefix={<GlobalOutlined />} placeholder="例如：京ICP备00000000号-1" size="large" style={{ borderRadius: 8 }} />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="icp_link" label={<span style={{ fontWeight: 500, color: "#475569" }}>备案链接</span>}>
                <Input placeholder="例如：https://beian.miit.gov.cn/" size="large" style={{ borderRadius: 8 }} />
              </Form.Item>
            </Col>
          </Row>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            onClick={submitSiteConfig}
            loading={siteSaving}
            size="large"
            style={{ borderRadius: 8, fontWeight: 500, boxShadow: "var(--shadow-smooth)" }}
          >
            保存站点展示
          </Button>
        </Form>
      </Card>

      {/* 底部：拆分导流区 */}
      <Card
        bordered={false}
        style={{ ...cardStyle, marginTop: 20, background: "linear-gradient(135deg, var(--glass-bg) 0%, var(--surface-soft) 100%)" }}
        bodyStyle={{ padding: 20 }}
      >
        <Row align="middle" justify="space-between" gutter={[16, 16]}>
          <Col xs={24} md={16}>
            <Typography.Title level={5} style={{ margin: 0, fontWeight: 600, color: "var(--text-main)" }}>
              核心管理模块调整
            </Typography.Title>
            <Typography.Paragraph type="secondary" style={{ margin: "4px 0 0 0", fontSize: 13 }}>
              为了提供更细粒度的权限隔离与后续的高级路由扩展，用户账号及节点集群管理已全面升级为独立菜单。
            </Typography.Paragraph>
          </Col>
          <Col xs={24} md={8} style={{ textAlign: isMobile ? "left" : "right" }}>
            <Space size={12} wrap style={{ width: isMobile ? "100%" : "auto" }}>
              <Button type="default" icon={<UserOutlined />} onClick={() => navigate("/settings/users")} style={{ borderRadius: 8, borderColor: "#cbd5e1" }}>
                用户管理入口
              </Button>
              <Button type="default" icon={<ClusterOutlined />} onClick={() => navigate("/settings/nodes")} style={{ borderRadius: 8, borderColor: "#cbd5e1" }}>
                节点集群管理
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>
    </div>
  );
}
