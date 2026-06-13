import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Button, Dropdown, Grid, Menu, Space, Typography } from "antd";
import {
  ClusterOutlined,
  DashboardOutlined,
  DownOutlined,
  HistoryOutlined,
  BgColorsOutlined,
  HeartOutlined,
  LogoutOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useAuth } from "../api/auth";
import { CuteBrandIcon, CuteStickerCluster } from "../components/CuteDecor";
import SiteFooter from "../components/SiteFooter";
import { useTheme } from "../theme/ThemeProvider";

const { useBreakpoint } = Grid;

export default function ShellLayout() {
  const { user, logout } = useAuth();
  const { theme, themeLabel, themeOptions, setTheme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const displayName = user?.nickname || user?.username || "管理员";

  const menuItems = [
    { key: "/", icon: <DashboardOutlined />, label: "资产总览" },
    { key: "/customers", icon: <TeamOutlined />, label: "客户管理" },
    { key: "/profile", icon: <UserOutlined />, label: "个人中心" },
    ...(user?.role === "admin" ? [{ key: "/settings/nodes", icon: <ClusterOutlined />, label: "节点集群" }] : []),
    ...(user?.role === "admin" ? [{ key: "/settings/users", icon: <UserOutlined />, label: "用户管理" }] : []),
    ...(user?.role === "admin" ? [{ key: "/settings", icon: <SettingOutlined />, label: "系统设置" }] : []),
    ...(user?.role === "admin" ? [{ key: "/system/health", icon: <HeartOutlined />, label: "系统健康" }] : []),
    ...(user?.role === "admin" ? [{ key: "/logs", icon: <HistoryOutlined />, label: "日志中心" }] : []),
  ];

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="apple-shell-container">
      <CuteStickerCluster />
      <style>{`
        body {
          background-color: var(--bg-apple) !important;
          color: var(--text-main);
          margin: 0;
          font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
          -webkit-font-smoothing: antialiased;
        }
        .apple-shell-container {
          display: flex;
          min-height: 100vh;
          flex-direction: ${isMobile ? "column" : "row"};
        }
        .apple-sidebar {
          width: 250px;
          background: var(--glass-bg);
          border-right: 1px solid var(--glass-border);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          padding: 28px 18px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          position: fixed;
          height: 100vh;
          z-index: 100;
        }
        .apple-mobile-navbar {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          height: calc(52px + env(safe-area-inset-top, 0px));
          background: var(--glass-bg);
          border-bottom: 1px solid var(--glass-border);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          z-index: 999;
          display: flex;
          align-items: center;
          justify-content: space-between;
          box-sizing: border-box;
          padding: env(safe-area-inset-top, 0px) 20px 0;
        }
        .apple-mobile-tabbar {
          position: fixed;
          bottom: 0;
          left: 0;
          right: 0;
          height: calc(68px + env(safe-area-inset-bottom, 0px));
          background: var(--glass-bg);
          border-top: 1px solid var(--glass-border);
          backdrop-filter: blur(25px);
          -webkit-backdrop-filter: blur(25px);
          z-index: 999;
          display: flex;
          justify-content: flex-start;
          align-items: stretch;
          overflow-x: auto;
          overflow-y: hidden;
          box-sizing: border-box;
          padding: 6px 0 max(env(safe-area-inset-bottom, 0px), 8px);
          scrollbar-width: none;
        }
        .apple-mobile-tabbar::-webkit-scrollbar {
          display: none;
        }
        .apple-mobile-tabbar.compact {
          justify-content: space-around;
          overflow-x: hidden;
        }
        .apple-tab-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          color: var(--text-sub);
          font-size: 10px;
          font-weight: 500;
          text-decoration: none;
          transition: color 0.15s ease;
          justify-content: center;
          height: 52px;
          padding: 3px 0 2px;
          box-sizing: border-box;
          flex: 0 0 68px;
          min-width: 68px;
        }
        .apple-mobile-tabbar.compact .apple-tab-item {
          flex: 1 1 0;
          min-width: 0;
          max-width: 140px;
        }
        .apple-tab-item.active {
          color: var(--apple-blue);
        }
        .apple-tab-item .anticon {
          font-size: 21px;
          margin-bottom: 3px;
        }
        .apple-main-viewport {
          flex: 1;
          margin-left: ${isMobile ? "0" : "250px"};
          padding: ${isMobile ? "calc(72px + env(safe-area-inset-top, 0px)) 14px calc(104px + env(safe-area-inset-bottom, 0px)) 14px" : "36px 40px"};
          background: var(--bg-apple);
          min-height: 100vh;
          box-sizing: border-box;
        }
        .ant-menu-inline { background: transparent !important; border: none !important; }
        .ant-menu-item { border-radius: 12px !important; height: 42px !important; line-height: 42px !important; }
        .ant-menu-item-selected { background-color: color-mix(in srgb, var(--apple-blue) 12%, transparent) !important; color: var(--apple-blue) !important; }
        .apple-user-pill {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px;
          background: rgba(0, 0, 0, 0.02);
          border-radius: 14px;
          border: 1px solid var(--glass-border);
          cursor: pointer;
        }
        .apple-theme-toggle {
          width: 100%;
          justify-content: flex-start;
          border-radius: 14px !important;
          background: var(--surface-soft);
          color: var(--text-main);
          border-color: var(--glass-border);
        }
        .cute-brand {
          display: flex;
          align-items: center;
          gap: 10px;
        }
      `}</style>

      {!isMobile && (
        <div className="apple-sidebar">
          <div>
            <div className="cute-brand" style={{ padding: "0 12px", marginBottom: 28 }}>
              <CuteBrandIcon size={42} />
              <div>
                <Typography.Title level={4} style={{ margin: 0, fontWeight: 700, letterSpacing: "-0.5px" }}>
                  SubSentry
                </Typography.Title>
                <Typography.Text style={{ fontSize: 11, color: "var(--text-sub)", fontWeight: 500 }}>
                  订阅资产风控系统
                </Typography.Text>
              </div>
            </div>
            <Menu
              mode="inline"
              selectedKeys={[location.pathname]}
              onClick={({ key }) => navigate(key)}
              items={menuItems.map((item) => ({ key: item.key, icon: item.icon, label: item.label }))}
            />
          </div>

          <Space direction="vertical" size={10} style={{ width: "100%" }}>
            <Dropdown
              menu={{
                selectedKeys: [theme],
                items: themeOptions.map((item) => ({
                  key: item.value,
                  label: item.label,
                  onClick: () => setTheme(item.value),
                })),
              }}
              trigger={["click"]}
            >
              <Button className="apple-theme-toggle" icon={<BgColorsOutlined />} onClick={(event) => event.preventDefault()}>
                {themeLabel} 主题
              </Button>
            </Dropdown>
            <Dropdown
              menu={{ items: [{ key: "logout", label: "退出当前登录", icon: <LogoutOutlined />, onClick: handleLogout }] }}
              placement="topRight"
              trigger={["click"]}
            >
              <div className="apple-user-pill">
                <Space size={10}>
                  <div style={{ background: "var(--apple-blue)", width: 34, height: 34, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontWeight: 600 }}>
                    {displayName.slice(0, 1).toUpperCase() || "A"}
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-main)" }}>{displayName}</div>
                    <div style={{ fontSize: 11, color: "var(--text-sub)" }}>{user?.username || "admin"}</div>
                  </div>
                </Space>
                <DownOutlined style={{ color: "var(--text-sub)", fontSize: 10 }} />
              </div>
            </Dropdown>
          </Space>
        </div>
      )}

      {isMobile && (
        <div className="apple-mobile-navbar">
          <div className="cute-brand">
            <CuteBrandIcon size={32} />
            <Typography.Title level={5} style={{ margin: 0, fontWeight: 700, letterSpacing: "-0.3px" }}>
              SubSentry
            </Typography.Title>
          </div>
          <Space size={8}>
            <Button size="small" shape="circle" icon={<BgColorsOutlined />} onClick={toggleTheme} title={`切换主题：当前 ${themeLabel}`} />
            <Dropdown menu={{ items: [{ key: "logout", label: "退出登录", icon: <LogoutOutlined />, onClick: handleLogout }] }}>
              <div style={{ background: "var(--apple-blue)", width: 28, height: 28, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", fontSize: 12, fontWeight: 600, boxShadow: "0 2px 8px rgba(0,113,227,0.2)" }}>
                {displayName.slice(0, 1).toUpperCase() || "A"}
              </div>
            </Dropdown>
          </Space>
        </div>
      )}

      <div className="apple-main-viewport">
        <Outlet />
        <SiteFooter />
      </div>

      {isMobile && (
        <div className={`apple-mobile-tabbar ${menuItems.length <= 4 ? "compact" : "scrollable"}`}>
          {menuItems.map((item) => {
            const isActive = item.key === "/" ? location.pathname === "/" : location.pathname.startsWith(item.key);
            return (
              <Link key={item.key} to={item.key} className={`apple-tab-item ${isActive ? "active" : ""}`}>
                {item.icon}
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

