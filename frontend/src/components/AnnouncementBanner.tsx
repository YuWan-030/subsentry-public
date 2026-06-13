import { Alert, Grid } from "antd";
import { NotificationOutlined } from "@ant-design/icons";
import type { SiteConfig } from "../api/settings";

const { useBreakpoint } = Grid;

export default function AnnouncementBanner({ config }: { config: SiteConfig | null }) {
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const text = (config?.announcement_text || "").trim();

  if (!config?.announcement_enabled || !text) {
    return null;
  }

  return (
    <Alert
      className="announcement-banner"
      type="info"
      showIcon
      icon={<NotificationOutlined />}
      message={
        <div className="announcement-marquee" aria-label={text}>
          <span>{text}</span>
        </div>
      }
      style={{ marginBottom: isMobile ? 12 : 18 }}
    />
  );
}
