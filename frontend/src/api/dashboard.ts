import api from "./http";

export type DashboardPeriod = "today" | "week" | "month";

export type DashboardSummary = {
  total_count: number;
  healthy_count: number;
  disabled_count: number;
  expired_count: number;
  warning_count: number;
  month_income: number;
};

export type MonthlyIncomeItem = {
  month: string;
  income: number;
};

export async function fetchDashboardSummary(period: DashboardPeriod = "month"): Promise<DashboardSummary> {
  const response = await api.get("/api/v1/dashboard/summary", { params: { period } });
  return response.data.data as DashboardSummary;
}

export async function fetchDashboardStatus(force = false): Promise<Omit<DashboardSummary, "month_income">> {
  const response = await api.get("/api/v1/dashboard/status", { params: force ? { force: true } : undefined });
  return response.data.data as Omit<DashboardSummary, "month_income">;
}

export async function fetchDashboardIncome(period: DashboardPeriod = "month", force = false): Promise<number> {
  const response = await api.get("/api/v1/dashboard/income", { params: { period, ...(force ? { force: true } : {}) } });
  return Number(response.data.data?.month_income || 0);
}

export async function fetchMonthlyIncome(period: DashboardPeriod = "month", force = false): Promise<MonthlyIncomeItem[]> {
  const response = await api.get("/api/v1/dashboard/income-monthly", { params: { period, ...(force ? { force: true } : {}) } });
  return response.data.data.series as MonthlyIncomeItem[];
}
