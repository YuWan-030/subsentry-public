import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Card, Result, Spin, Typography } from "antd";
import { useNavigate, useSearchParams } from "react-router-dom";
import { finishOnAuthCallback, useAuth } from "../api/auth";
import SiteFooter from "../components/SiteFooter";
import { extractErrorMessage } from "../utils/feedback";

const submittedCallbacks = new Set<string>();
const CALLBACK_LOCK_PREFIX = "subsentry:onauth-callback:";

export default function OnAuthCallbackPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [error, setError] = useState("");
  const [redirectSeconds, setRedirectSeconds] = useState(3);
  const redirectUri = useMemo(() => `${window.location.origin}/onauth/callback`, []);
  const submittedRef = useRef("");
  const searchKey = useMemo(() => {
    const code = searchParams.get("code") || "";
    const state = searchParams.get("state") || "";
    return `${state}:${code}`;
  }, [searchParams]);

  useEffect(() => {
    const code = searchParams.get("code") || "";
    const state = searchParams.get("state") || "";
    if (!code || !state) {
      setError("OnAuth 回调缺少 code 或 state");
      return;
    }
    const callbackKey = `${state}:${code}`;
    const storageKey = `${CALLBACK_LOCK_PREFIX}${callbackKey}`;
    if (submittedRef.current === callbackKey || submittedCallbacks.has(callbackKey) || window.sessionStorage.getItem(storageKey)) {
      return;
    }
    submittedRef.current = callbackKey;
    submittedCallbacks.add(callbackKey);
    window.sessionStorage.setItem(storageKey, "pending");
    const run = async () => {
      try {
        const result = await finishOnAuthCallback({ code, state, redirect_uri: redirectUri });
        window.sessionStorage.setItem(storageKey, "done");
        await refreshUser();
        window.setTimeout(() => {
          navigate(result.data?.mode === "bind" ? "/profile" : "/", { replace: true });
        }, 500);
      } catch (err: any) {
        window.sessionStorage.setItem(storageKey, "failed");
        if (err?.response?.status === 403 && String(err?.response?.data?.detail || err?.message || "").includes("禁用")) {
          navigate("/login/disabled", {
            replace: true,
            state: { message: err?.response?.data?.detail || "当前账号已被禁用，请联系管理员处理。" },
          });
          return;
        }
        setRedirectSeconds(3);
        setError(extractErrorMessage(err, "OnAuth 回调处理失败"));
      }
    };
    void run();
  }, [navigate, redirectUri, refreshUser, searchKey, searchParams]);

  useEffect(() => {
    if (!error) {
      return;
    }
    const tickTimer = window.setInterval(() => {
      setRedirectSeconds((seconds) => Math.max(seconds - 1, 0));
    }, 1000);
    const redirectTimer = window.setTimeout(() => {
      navigate("/login", { replace: true });
    }, 3200);
    return () => {
      window.clearInterval(tickTimer);
      window.clearTimeout(redirectTimer);
    };
  }, [error, navigate]);

  if (error) {
    return (
      <div className="login-shell">
        <Card className="login-card" bordered={false}>
          <Result
            status="error"
            title="OnAuth 处理失败"
            subTitle={error}
            extra={
              <>
                <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
                  {redirectSeconds} 秒后返回登录页
                </Typography.Paragraph>
                <Button type="primary" onClick={() => navigate("/login", { replace: true })}>
                  返回登录页
                </Button>
              </>
            }
          />
        </Card>
        <SiteFooter fixed />
      </div>
    );
  }

  return (
    <div className="login-shell">
      <Card className="login-card" bordered={false}>
        <Result icon={<Spin size="large" />} title="正在完成 OnAuth 授权..." />
      </Card>
      <SiteFooter fixed />
    </div>
  );
}
