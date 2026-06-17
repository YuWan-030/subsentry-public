import api from "./http";
import type { PageResult } from "./logs";

export type FinancialLogRow = {
  id: number;
  customer_id?: number;
  owner_username?: string;
  node_id?: number;
  node_name?: string;
  remote_email?: string;
  customer_name: string;
  renew_price: string;
  amount?: number;
  renew_days: number;
  new_expiry: string;
  created_at: string;
};

export type FinancialLogUpdatePayload = {
  customer_name?: string;
  owner_username?: string;
  renew_price?: string;
  amount?: number;
  renew_days?: number;
  new_expiry?: string;
  created_at?: string;
};

export type FinancialLogPage = PageResult<FinancialLogRow> & {
  total_amount: number;
};

export async function fetchFinancialLogs(params: {
  page?: number;
  per_page?: number;
  keyword?: string;
  owner_username?: string;
  node_id?: number | string;
  date_from?: string;
  date_to?: string;
} = {}) {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== "" && value !== undefined && value !== null),
  );
  const response = await api.get("/api/v1/finance/logs", { params: cleanParams });
  return response.data.data as FinancialLogPage;
}

export async function updateFinancialLog(logId: number, payload: FinancialLogUpdatePayload) {
  const response = await api.put(`/api/v1/finance/logs/${logId}`, payload);
  return response.data as { success: boolean; message: string; data: FinancialLogRow };
}

export async function deleteFinancialLog(logId: number) {
  const response = await api.delete(`/api/v1/finance/logs/${logId}`);
  return response.data as { success: boolean; message: string };
}
