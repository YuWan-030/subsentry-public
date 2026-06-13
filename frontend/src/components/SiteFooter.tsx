import { useEffect, useState } from "react";
import { fetchSiteConfig, type SiteConfig } from "../api/settings";

export default function SiteFooter({ fixed = false }: { fixed?: boolean }) {
  const [config, setConfig] = useState<SiteConfig | null>(null);
  const icpNumber = (config?.icp_number || "").trim();
  const icpLink = (config?.icp_link || "").trim();

  useEffect(() => {
    fetchSiteConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
    const handleUpdated = (event: Event) => {
      const nextConfig = (event as CustomEvent<SiteConfig>).detail;
      if (nextConfig) {
        setConfig(nextConfig);
      }
    };
    window.addEventListener("subsentry-site-config-updated", handleUpdated);
    return () => window.removeEventListener("subsentry-site-config-updated", handleUpdated);
  }, []);

  if (!icpNumber) {
    return null;
  }

  const content = icpLink ? (
    <a href={icpLink} target="_blank" rel="noreferrer">
      {icpNumber}
    </a>
  ) : (
    <span>{icpNumber}</span>
  );

  return <footer className={`site-footer ${fixed ? "site-footer-fixed" : ""}`}>{content}</footer>;
}
