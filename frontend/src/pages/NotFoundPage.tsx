import { Button, Card, Result, Space, Typography } from "antd";
import { HomeOutlined, LoginOutlined, QuestionCircleOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { CuteBrandIcon } from "../components/CuteDecor";
import SiteFooter from "../components/SiteFooter";
import { useAuth } from "../api/auth";

export default function NotFoundPage() {
  const navigate = useNavigate();
  const { user } = useAuth();

  return (
    <div className="not-found-shell">
      <Card className="not-found-card" bordered={false}>
        <div className="not-found-brand">
          <CuteBrandIcon size={46} />
          <div>
            <Typography.Title level={4} style={{ margin: 0, color: "var(--text-main)" }}>
              SubSentry
            </Typography.Title>
            <Typography.Text style={{ color: "var(--text-sub)" }}>订阅资产管理中心</Typography.Text>
          </div>
        </div>
        <Result
          icon={<QuestionCircleOutlined style={{ color: "var(--apple-blue)" }} />}
          title="页面不存在"
          subTitle="当前地址没有对应页面，可能是链接已失效或路径输入有误。"
          extra={
            <Space wrap>
              <Button type="primary" icon={<HomeOutlined />} onClick={() => navigate("/", { replace: true })}>
                返回首页
              </Button>
              {!user ? (
                <Button icon={<LoginOutlined />} onClick={() => navigate("/login", { replace: true })}>
                  去登录
                </Button>
              ) : null}
            </Space>
          }
        />
      </Card>
      <SiteFooter fixed />
    </div>
  );
}
