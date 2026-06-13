import { Button, Card, Result, Typography } from "antd";
import { LoginOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { CuteBrandIcon, CuteStickerCluster } from "../components/CuteDecor";
import SiteFooter from "../components/SiteFooter";

type DisabledLocationState = {
  message?: string;
};

export default function AccountDisabledPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [seconds, setSeconds] = useState(4);
  const message = (location.state as DisabledLocationState | null)?.message || "当前账号已被禁用，请联系管理员处理。";

  useEffect(() => {
    const tickTimer = window.setInterval(() => {
      setSeconds((current) => Math.max(current - 1, 0));
    }, 1000);
    const redirectTimer = window.setTimeout(() => {
      navigate("/login", { replace: true });
    }, 4200);
    return () => {
      window.clearInterval(tickTimer);
      window.clearTimeout(redirectTimer);
    };
  }, [navigate]);

  return (
    <div className="login-shell">
      <CuteStickerCluster />
      <Card className="login-card" bordered={false}>
        <div className="login-brand-row" style={{ marginBottom: 8 }}>
          <CuteBrandIcon size={42} />
          <Typography.Title level={3} style={{ margin: 0 }}>
            SubSentry
          </Typography.Title>
        </div>
        <Result
          status="warning"
          title="账号不可用"
          subTitle={message}
          extra={
            <>
              <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
                {seconds} 秒后返回登录页
              </Typography.Paragraph>
              <Button type="primary" icon={<LoginOutlined />} onClick={() => navigate("/login", { replace: true })}>
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
