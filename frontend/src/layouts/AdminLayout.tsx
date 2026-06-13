import { Layout, Menu, Tag, Typography } from "antd";
import { DashboardOutlined, SettingOutlined, TeamOutlined, UserOutlined } from "@ant-design/icons";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../api/auth";
const { Header, Sider, Content } = Layout;
const items = [
  { key: "/", icon: <DashboardOutlined />, label: <Link to="/">资产总览</Link> },
  { key: "/customers", icon: <TeamOutlined />, label: <Link to="/customers">客户管理</Link> },
  {
    key: "/settings",
    icon: <SettingOutlined />,
    label: "系统设置",
    children: [
      { key: "/settings", icon: <SettingOutlined />, label: <Link to="/settings">概览</Link> },
      { key: "/settings/users", icon: <UserOutlined />, label: <Link to="/settings/users">用户管理</Link> },
      { key: "/settings/nodes", icon: <SettingOutlined />, label: <Link to="/settings/nodes">节点管理</Link> },
    ],
  },
];
export default function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  return (
    <Layout style={{ minHeight: "100vh", background: "linear-gradient(180deg, #f5f7fb 0%, #eef3ff 100%)" }}>
      <Sider
        breakpoint="lg"
        collapsible
        style={{ background: "rgba(17, 24, 39, 0.92)", backdropFilter: "blur(18px)", paddingTop: 8 }}
      >
        <div style={{ height: 64, color: "#fff", display: "grid", placeItems: "center", fontWeight: 800, letterSpacing: 0.5 }}>
          SubSentry
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[
            location.pathname.startsWith("/customers") ? "/customers" :
            location.pathname.startsWith("/settings/users") ? "/settings/users" :
            location.pathname.startsWith("/settings/nodes") ? "/settings/nodes" :
            location.pathname.startsWith("/settings") ? "/settings" : "/",
          ]}
          items={items}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "rgba(255,255,255,0.74)", backdropFilter: "blur(18px)", display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: "1px solid rgba(15,23,42,0.06)" }}>
          <div>
            <Typography.Text strong>当前用户：{user?.username || "未登录"}</Typography.Text>
            <Tag color={user?.role === "admin" ? "blue" : "default"} style={{ marginLeft: 12 }}>
              {user?.role || "user"}
            </Tag>
          </div>
          <a onClick={async () => { await logout(); navigate("/login"); }}>
            退出登录
          </a>
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
