import api from "./http";

export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  per_page: number;
};

export type ActivityLogRow = {
  id: number;
  category: string;
  action: string;
  actor?: string;
  target_type?: string;
  target_id?: string;
  target_name?: string;
  status: string;
  summary: string;
  detail?: string;
  ip_address?: string;
  created_at: string;
};

export type NotificationLogRow = {
  id: number;
  event_type: string;
  send_mode: string;
  customer_id?: string;
  node_id?: number;
  remote_email?: string;
  customer_name?: string;
  manager?: string;
  webhook_url?: string;
  status: string;
  response_status?: number;
  response_text?: string;
  error_message?: string;
  retry_count: number;
  last_retry_at?: string;
  created_at: string;
  sent_at?: string;
};

export async function fetchActivityLogs(params: {
  page?: number;
  per_page?: number;
  category?: string;
  keyword?: string;
} = {}) {
  const response = await api.get("/api/v1/logs/activity", { params });
  return response.data.data as PageResult<ActivityLogRow>;
}

export async function fetchActivityCategories() {
  const response = await api.get("/api/v1/logs/activity/categories");
  return response.data.data as string[];
}

export async function fetchNotificationLogs(params: {
  page?: number;
  per_page?: number;
  status?: string;
  event_type?: string;
  customer_id?: string;
} = {}) {
  const response = await api.get("/api/v1/logs/notifications", { params });
  return response.data.data as PageResult<NotificationLogRow>;
}

export async function retryNotificationLog(logId: number) {
  const response = await api.post(`/api/v1/logs/notifications/${logId}/retry`);
  return response.data as { success: boolean; message: string };
}
