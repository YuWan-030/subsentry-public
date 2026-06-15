import { BgColorsOutlined } from "@ant-design/icons";
import { Button, Card, Divider, Form, Input, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchOnAuthConfig, fetchTurnstileConfig, finishPasskeyAuthentication, startOnAuth, startPasskeyAuthentication } from "../api/auth";
import api from "../api/http";
import { CuteBrandIcon, CuteStickerCluster } from "../components/CuteDecor";
import SiteFooter from "../components/SiteFooter";
import { useTheme } from "../theme/ThemeProvider";
import { dismissActionFeedback, extractErrorMessage, notifyActionError, notifyActionLoading, notifyActionSuccess, notifyActionWarning } from "../utils/feedback";
import { credentialToJSON, isPasskeyAbortError, isPasskeySupported, normalizeRequestOptions } from "../utils/webauthn";

function OnAuthIcon({ size = 18 }: { size?: number }) {
  return <img src="/onauth.ico" alt="" aria-hidden="true" style={{ width: size, height: size, objectFit: "contain" }} />;
}

function loadTurnstileScript() {
  const scriptId = "cf-turnstile-script";
  const existing = document.getElementById(scriptId) as HTMLScriptElement | null;
  if (window.turnstile) {
    return Promise.resolve();
  }
  if (existing) {
    return new Promise<void>((resolve, reject) => {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("Turnstile script failed to load")), { once: true });
    });
  }

  return new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.id = scriptId;
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Turnstile script failed to load"));
    document.head.appendChild(script);
  });
}

function TurnstileBox({ siteKey, onTokenChange }: { siteKey: string; onTokenChange: (token: string) => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetIdRef = useRef<string | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let disposed = false;
    onTokenChange("");
    setStatus("loading");
    loadTurnstileScript()
      .then(() => {
        if (disposed || !window.turnstile || !containerRef.current) {
          return;
        }
        setStatus("ready");
        widgetIdRef.current = window.turnstile.render(containerRef.current, {
          sitekey: siteKey,
          theme: "auto",
          appearance: "always",
          callback: (token) => onTokenChange(token),
          "expired-callback": () => onTokenChange(""),
          "error-callback": () => {
            onTokenChange("");
            setStatus("error");
          },
        });
      })
      .catch(() => {
        onTokenChange("");
        setStatus("error");
      });

    return () => {
      disposed = true;
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
      }
      widgetIdRef.current = null;
    };
  }, [onTokenChange, siteKey]);

  return (
    <div className="turnstile-wrap">
      <div ref={containerRef} />
      {status === "loading" ? <span className="turnstile-hint">正在加载人机验证...</span> : null}
      {status === "error" ? <span className="turnstile-hint">人机验证加载失败，请刷新页面</span> : null}
    </div>
  );
}

export default function LoginPage({ onSuccess }: { onSuccess: () => void }) {
  const { themeLabel, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [onauthEnabled, setOnauthEnabled] = useState(false);
  const [onauthLoading, setOnauthLoading] = useState(false);
  const [passkeyLoading, setPasskeyLoading] = useState(false);
  const [turnstileEnabled, setTurnstileEnabled] = useState(false);
  const [turnstileSiteKey, setTurnstileSiteKey] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("");
  const [turnstileNonce, setTurnstileNonce] = useState(0);
  const passkeySupported = isPasskeySupported();

  useEffect(() => {
    fetchOnAuthConfig()
      .then((config) => setOnauthEnabled(config.enabled))
      .catch(() => setOnauthEnabled(false));
    fetchTurnstileConfig()
      .then((config) => {
        setTurnstileEnabled(config.enabled);
        setTurnstileSiteKey(config.site_key || "");
      })
      .catch(() => {
        setTurnstileEnabled(false);
        setTurnstileSiteKey("");
      });
  }, []);

  const onFinish = async (values: { username: string; password: string }) => {
    if (turnstileEnabled && !turnstileToken) {
      notifyActionError("login-submit", "请先完成人机验证");
      return;
    }
    try {
      notifyActionLoading("login-submit", "登录中...");
      await api.post("/api/v1/auth/login", { ...values, turnstile_token: turnstileToken });
      notifyActionSuccess("login-submit", "登录成功");
      onSuccess();
    } catch (error: any) {
      if (turnstileEnabled) {
        setTurnstileToken("");
        setTurnstileNonce((value) => value + 1);
      }
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
          {turnstileEnabled && turnstileSiteKey ? (
            <Form.Item>
              <TurnstileBox key={turnstileNonce} siteKey={turnstileSiteKey} onTokenChange={setTurnstileToken} />
            </Form.Item>
          ) : null}
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
