import { BgColorsOutlined } from "@ant-design/icons";
import { Button, Card, Divider, Form, Input, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchOnAuthConfig, finishPasskeyAuthentication, startOnAuth, startPasskeyAuthentication } from "../api/auth";
import api from "../api/http";
import { CuteBrandIcon, CuteStickerCluster } from "../components/CuteDecor";
import SiteFooter from "../components/SiteFooter";
import { useTheme } from "../theme/ThemeProvider";
import { dismissActionFeedback, extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess, notifyActionWarning } from "../utils/feedback";
import { credentialToJSON, isPasskeyAbortError, isPasskeySupported, normalizeRequestOptions } from "../utils/webauthn";

function OnAuthIcon({ size = 18 }: { size?: number }) {
  return <img src="/onauth.ico" alt="" aria-hidden="true" style={{ width: size, height: size, objectFit: "contain" }} />;
}

export default function LoginPage({ onSuccess }: { onSuccess: () => void }) {
  const { themeLabel, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [onauthEnabled, setOnauthEnabled] = useState(false);
  const [onauthLoading, setOnauthLoading] = useState(false);
  const [passkeyLoading, setPasskeyLoading] = useState(false);
  const passkeySupported = isPasskeySupported();

  useEffect(() => {
    fetchOnAuthConfig()
      .then((config) => setOnauthEnabled(config.enabled))
      .catch(() => setOnauthEnabled(false));
  }, []);

  const onFinish = async (values: { username: string; password: string }) => {
    try {
      notifyActionLoading("login-submit", "登录中...");
      await api.post("/api/v1/auth/login", values);
      notifyActionSuccess("login-submit", "登录成功");
      onSuccess();
    } catch (error: any) {
      if (error?.response?.status === 403 && String(error?.response?.data?.detail || error?.message || "").includes("禁用")) {
        dismissActionFeedback("login-submit");
        navigate("/login/disabled", {
          replace: true,
          state: { message: error?.response?.data?.detail || "当前账号已被禁用，请联系管理员处理。" },
        });
        return;
      }
      notifyActionError("login-submit", extractErrorMessage(error, "登录失败"));
    }
  };

  const loginWithPasskey = async () => {
    if (!passkeySupported) {
      notifyActionError("passkey-login", "当前浏览器不支持 Passkey");
      return;
    }
    try {
      setPasskeyLoading(true);
      const username = (form.getFieldValue("username") || "").trim() || undefined;
      const origin = window.location.origin;
      const result = await startPasskeyAuthentication(origin, username);
      const credential = await navigator.credentials.get({ publicKey: normalizeRequestOptions(result.options) });
      if (!credential) {
        throw new Error("未获取到 Passkey 凭证");
      }
      const verified = await finishPasskeyAuthentication({
        challenge_id: result.challenge_id,
        origin,
        credential: credentialToJSON(credential),
      });
      notifyActionSuccess("passkey-login", verified.message || "Passkey 登录成功");
      onSuccess();
    } catch (error: any) {
      if (isPasskeyAbortError(error)) {
        notifyActionWarning("passkey-login", "Passkey 验证失败或已主动取消");
        return;
      }
      if (error?.response?.status === 403 && String(error?.response?.data?.detail || error?.message || "").includes("禁用")) {
        dismissActionFeedback("passkey-login");
        navigate("/login/disabled", {
          replace: true,
          state: { message: error?.response?.data?.detail || "当前账号已被禁用，请联系管理员处理。" },
        });
        return;
      }
      notifyActionError("passkey-login", extractErrorMessage(error, "Passkey 登录失败"));
    } finally {
      setPasskeyLoading(false);
    }
  };

  const loginWithOnAuth = async () => {
    try {
      setOnauthLoading(true);
      const redirectUri = `${window.location.origin}/onauth/callback`;
      const result = await startOnAuth("login", redirectUri);
      window.location.href = result.authorize_url;
    } catch (error: any) {
      notifyActionError("onauth-login", extractErrorMessage(error, "OnAuth 登录启动失败"));
      setOnauthLoading(false);
    }
  };

  return (
    <div className="login-shell">
      <CuteStickerCluster />
      <Button className="login-theme-button" icon={<BgColorsOutlined />} onClick={toggleTheme}>
        {themeLabel}
      </Button>
      <Card className="login-card" bordered={false}>
        <div style={{ marginBottom: 24 }}>
          <div className="login-brand-row">
            <CuteBrandIcon size={46} />
            <Typography.Title level={2} style={{ marginTop: 0, marginBottom: 8 }}>
              SubSentry
            </Typography.Title>
          </div>
          <Typography.Text type="secondary">订阅资产管理中心</Typography.Text>
        </div>
        <Form form={form} layout="vertical" onFinish={onFinish}>
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input size="large" placeholder="请输入用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password size="large" placeholder="请输入密码" autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block size="large" style={{ borderRadius: 12 }}>
            登录
          </Button>
        </Form>
        {passkeySupported ? (
          <>
            <Divider plain>或</Divider>
            <Button block size="large" loading={passkeyLoading} onClick={() => void loginWithPasskey()}>
              使用 Passkey 登录
            </Button>
          </>
        ) : null}
        {onauthEnabled ? (
          <>
            <Divider plain>或</Divider>
            <Button block size="large" icon={<OnAuthIcon />} loading={onauthLoading} onClick={() => void loginWithOnAuth()}>
              使用 OnAuth 登录
            </Button>
          </>
        ) : null}
      </Card>
      <SiteFooter fixed />
    </div>
  );
}
