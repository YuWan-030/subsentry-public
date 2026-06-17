import api from "./http";

export type SettingsOptions = {
  success: boolean;
  nodes: Array<{
    id: number;
    name: string;
    display_name: string;
    scheme: string;
    address: string;
    port: number;
    base_path: string;
    subscription_scheme: "http" | "https";
    subscription_address: string;
    subscription_port: number;
    subscription_sub_path: string;
    subscription_json_path: string;
    subscription_clash_path: string;
    allow_insecure: boolean;
    last_status: string;
    last_message: string;
    last_checked_at?: string;
    last_latency_ms?: number;
    consecutive_failures?: number;
    abnormal_notified_at?: string;
  }>;
  managers: Array<{ id: number; name: string; username?: string; nickname?: string; role?: string }>;
  notification: {
    push_mode: "per_customer" | "summary" | "hybrid" | "manager_summary";
    max_detail_rows: number;
    fixed_push_time: string;
    fixed_push_time_enabled: boolean;
    push_time_window_minutes: number;
  };
};

export async function fetchSettingsOptions(): Promise<SettingsOptions> {
  const response = await api.get("/api/v1/settings/options");
  return response.data as SettingsOptions;
}

export type SiteConfig = {
  announcement_enabled: boolean;
  announcement_text: string;
  icp_number: string;
  icp_link: string;
};

export type LocalSubscriptionConfig = {
  enabled: boolean;
  base_url: string;
  port: number;
  title: string;
};

export async function fetchSiteConfig() {
  const response = await api.get("/api/v1/settings/site-public");
  return response.data.data as SiteConfig;
}

export async function fetchAdminSiteConfig() {
  const response = await api.get("/api/v1/settings/site-config");
  return response.data.data as SiteConfig;
}

export async function saveSiteConfig(payload: SiteConfig) {
  const response = await api.post("/api/v1/settings/site-config", payload);
  window.dispatchEvent(new CustomEvent("subsentry-site-config-updated", { detail: payload }));
  return response.data as { success: boolean; message: string };
}

export async function fetchLocalSubscriptionConfig() {
  const response = await api.get("/api/v1/settings/local-subscription-config");
  return response.data.data as LocalSubscriptionConfig;
}

export async function saveLocalSubscriptionConfig(payload: LocalSubscriptionConfig) {
  const response = await api.post("/api/v1/settings/local-subscription-config", payload);
  return response.data as { success: boolean; message: string; data: LocalSubscriptionConfig };
}

export type NotificationTemplatePayload = {
  notification_template: string;
  notification_template_traffic_low?: string;
  notification_template_customer_disabled?: string;
  notification_template_node_abnormal?: string;
  notification_template_summary?: string;
};

export async function saveNotificationTemplate(payload: string | NotificationTemplatePayload) {
  const body = typeof payload === "string" ? { notification_template: payload } : payload;
  const response = await api.post("/api/v1/settings/notification-template", body);
  return response.data as { success: boolean; message: string };
}

export async function saveNotificationConfig(payload: {
  push_mode: string;
  max_detail_rows: number;
  fixed_push_time: string;
  fixed_push_time_enabled: boolean;
  push_time_window_minutes: number;
}) {
  const response = await api.post("/api/v1/settings/notification-config", payload);
  return response.data as { success: boolean; message: string };
}

export type NodePayload = {
  name: string;
  scheme: "http" | "https";
  address: string;
  port: number;
  base_path: string;
  api_token: string;
  allow_insecure?: boolean;
  subscription_scheme?: "http" | "https";
  subscription_address?: string;
  subscription_port?: number;
  subscription_sub_path?: string;
  subscription_json_path?: string;
  subscription_clash_path?: string;
};

export async function addNode(payload: NodePayload) {
  const response = await api.post("/api/v1/settings/nodes", payload);
  return response.data as { success: boolean; message: string };
}

export async function updateNode(itemId: number, payload: NodePayload) {
  const response = await api.put(`/api/v1/settings/nodes/${itemId}`, payload);
  return response.data as { success: boolean; message: string };
}

export async function testNode(payload: NodePayload) {
  const response = await api.post("/api/v1/settings/nodes/test", payload);
  return response.data as { success: boolean; message: string; data: Record<string, unknown> };
}

export async function fetchNodeSubscriptionSettings(payload: NodePayload) {
  const response = await api.post("/api/v1/settings/nodes/subscription-settings", payload);
  return response.data as {
    success: boolean;
    message: string;
    data: Pick<NodePayload, "subscription_scheme" | "subscription_address" | "subscription_port" | "subscription_sub_path" | "subscription_json_path" | "subscription_clash_path">;
  };
}

export async function probeNode(itemId: number) {
  const response = await api.post(`/api/v1/settings/nodes/${itemId}/probe`);
  return response.data as { success: boolean; message: string; data: Record<string, unknown> };
}

export async function deleteNode(itemId: number) {
  const response = await api.delete(`/api/v1/settings/nodes/${itemId}`);
  return response.data as { success: boolean; message: string };
}

export async function addManager(name: string) {
  const response = await api.post("/api/v1/settings/managers", { name });
  return response.data as { success: boolean; message: string };
}

export async function deleteManager(itemId: number) {
  const response = await api.delete(`/api/v1/settings/managers/${itemId}`);
  return response.data as { success: boolean; message: string };
}
