import api from "./http";

export type CustomerRow = {
  id: string;
  name: string;
  manager: string;
  node: string;
  node_id: number;
  remote_email: string;
  sub_id?: string;
  renew_price: string;
  expiry_date: string;
  duration: string;
  traffic?: string;
  traffic_total_gb?: number;
  traffic_used_gb?: number;
  traffic_remaining_gb?: number | null;
  traffic_total_display?: string;
  traffic_used_display?: string;
  traffic_remaining_display?: string;
  is_unlimited_traffic?: boolean;
  webhook_url?: string;
  enable?: boolean;
  expiry_display?: string;
  is_unlimited_expiry?: boolean;
  inbound_ids?: number[];
  total_gb?: number;
  traffic_multiplier?: number;
  limit_ip?: number;
  inbounds?: Array<{ id: number; remark: string; protocol: string; port: number }>;
  remaining_days: number;
  status_text: string;
  status_level: "expired" | "today" | "warning" | "healthy" | "disabled" | "unlimited";
};

export type CustomerSubscription = {
  customer_id: string;
  name: string;
  node: string;
  sub_id: string;
  links: {
    standard?: string;
    json?: string;
    clash?: string;
  };
  remote_links?: {
    standard?: string;
    json?: string;
    clash?: string;
  };
  local_links?: {
    standard?: string;
    json?: string;
    clash?: string;
  };
  local_subscription?: {
    enabled: boolean;
    base_url: string;
    port: number;
    title: string;
  };
  protocol_links: string[];
};

export type CustomerListResponse = {
  count: number;
  data: CustomerRow[];
};

export type CustomerAuditRow = {
  id: number;
  customer_name: string;
  action: string;
  actor: string;
  change_summary: string;
  created_at: string;
};

export type CustomerRenewalRow = {
  id: number;
  customer_name: string;
  actor: string;
  renew_days: number;
  old_expiry: string;
  new_expiry: string;
  renew_price: string;
  created_at: string;
};

export type CustomerPayload = {
  name: string;
  manager?: string;
  node: string;
  node_id?: number;
  remote_email?: string;
  expiry_date?: string;
  renew_price?: string;
  webhook_url?: string;
  duration_mode?: "days" | "date";
  duration_days?: number;
  custom_expiry_date?: string;
  inbound_ids?: number[];
  total_gb?: number;
  traffic_multiplier?: number;
  enable?: boolean;
  limit_ip?: number;
};

export type RenewPayload = {
  renew_days: number;
  renew_price?: string;
};

export type BulkUpdateFieldsPayload = {
  customer_ids: string[];
  enable?: boolean;
  total_gb?: number;
  traffic_multiplier?: number;
  limit_ip?: number;
  renew_price?: string;
  duration_mode?: "days" | "date";
  duration_days?: number;
  custom_expiry_date?: string;
};

export async function fetchCustomers(params: { keyword?: string; node?: string; node_id?: number | string; manager?: string } = {}) {
  const response = await api.get("/api/v1/customers", { params });
  return response.data as { count: number; data: CustomerRow[] };
}

export async function fetchCustomerDetail(customerId: string) {
  const response = await api.get(`/api/v1/customers/${customerId}`);
  return response.data.data;
}

export async function createCustomer(payload: CustomerPayload) {
  const response = await api.post("/api/v1/customers", payload);
  return response.data as { success: boolean; message: string; customer_id?: string };
}

export async function updateCustomer(customerId: string, payload: Partial<CustomerPayload>) {
  const response = await api.put(`/api/v1/customers/${customerId}`, payload);
  return response.data as { success: boolean; message: string };
}

export async function deleteCustomer(customerId: string) {
  const response = await api.delete(`/api/v1/customers/${customerId}`);
  return response.data as { success: boolean; message: string };
}

export async function renewCustomer(customerId: string, payload: RenewPayload) {
  const response = await api.post(`/api/v1/customers/${customerId}/renew`, payload);
  return response.data as { success: boolean; message: string; new_expiry: string; renew_price: string };
}

export async function resetCustomerTraffic(customerId: string) {
  const response = await api.post(`/api/v1/customers/${customerId}/reset-traffic`);
  return response.data as { success: boolean; message: string; data?: CustomerRow };
}

export async function bulkAssignCustomerManager(customerIds: string[], manager: string) {
  const response = await api.post("/api/v1/customers/bulk/assign-manager", { customer_ids: customerIds, manager });
  return response.data as { success: boolean; message: string; total: number; updated: unknown[]; errors: Array<{ id: string; message: string }> };
}

export async function bulkUpdateCustomers(payload: BulkUpdateFieldsPayload) {
  const response = await api.post("/api/v1/customers/bulk/update-fields", payload);
  return response.data as { success: boolean; message: string; total: number; updated: unknown[]; errors: Array<{ id: string; message: string }> };
}

export async function fetchCustomerSubscription(customerId: string) {
  const response = await api.get(`/api/v1/customers/${customerId}/subscription`);
  return response.data.data as CustomerSubscription;
}

export async function fetchCustomerAudit(customerId: string) {
  const response = await api.get(`/api/v1/customers/${customerId}/audit`);
  return response.data.data as CustomerAuditRow[];
}

export async function fetchCustomerAuditByAction(customerId: string, action?: string) {
  const response = await api.get(`/api/v1/customers/${customerId}/audit`, { params: action ? { action } : undefined });
  return response.data.data as CustomerAuditRow[];
}

export async function fetchCustomerRenewals(customerId: string) {
  const response = await api.get(`/api/v1/customers/${customerId}/renewals`);
  return response.data.data as CustomerRenewalRow[];
}

export async function testCustomerWebhook(customerId: string) {
  const response = await api.post(`/api/v1/customers/${customerId}/test-webhook`);
  return response.data as { success: boolean; message: string };
}
