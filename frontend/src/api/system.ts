import api from "./http";

export type HealthActivity = {
  id?: number;
  category: string;
  action: string;
  actor: string;
  status: string;
  summary: string;
  detail?: unknown;
  created_at: string;
};

export type HealthNode = {
  id: number;
  name: string;
  address: string;
  port?: number;
  status: string;
  message: string;
  last_checked_at: string;
  latency_ms?: number;
};

export type SystemHealth = {
  backend: {
    status: string;
    ok: boolean;
    message: string;
    app_name: string;
    version: string;
    started_at: string;
    checked_at: string;
  };
  database: {
    status: string;
    ok: boolean;
    latency_ms?: number;
    message: string;
  };
  nodes: {
    status: string;
    message: string;
    total: number;
    online: number;
    offline: number;
    unknown: number;
    latest_checked_at: string;
    items: HealthNode[];
  };
  notification: {
    status: string;
    message: string;
    last_checked_at: string;
    last_check?: HealthActivity | null;
    latest_notification_log?: Record<string, unknown> | null;
  };
  latest_auto_task?: HealthActivity | null;
};

export async function fetchSystemHealth(): Promise<SystemHealth> {
  const response = await api.get("/api/v1/system/health");
  return response.data.data as SystemHealth;
}
