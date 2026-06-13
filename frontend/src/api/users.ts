import api from "./http";

export type UserRow = {
  id: number;
  username: string;
  nickname?: string;
  role: "admin" | "user";
  enabled: boolean;
  created_at: string;
  updated_at?: string;
};

export type UsersListResponse = { items: UserRow[]; total: number; page: number; per_page: number };

function normalizeEnabled(value: unknown): boolean {
  return value === true || value === 1 || String(value).toLowerCase() === "true";
}

export async function fetchUsers(params?: { page?: number; per_page?: number; keyword?: string; role?: string }): Promise<UsersListResponse> {
  const response = await api.get("/api/v1/auth/users", { params });
  const data = response.data.data as UsersListResponse;
  return {
    ...data,
    items: (data.items || []).map((item) => ({
      ...item,
      enabled: normalizeEnabled(item.enabled),
    })),
  };
}

export async function fetchUserAudit(userId: number) {
  const response = await api.get(`/api/v1/auth/users/${userId}/audit`);
  return response.data.data as Array<{ id: number; target_user_id: number; target_username: string; action: string; actor: string; change_summary: string; created_at: string }>;
}

export async function createUser(payload: { username: string; password: string; role?: "admin" | "user"; nickname?: string }) {
  const response = await api.post("/api/v1/auth/users", payload);
  return response.data as { success: boolean; message: string };
}

export async function deleteUser(userId: number) {
  const response = await api.delete(`/api/v1/auth/users/${userId}`);
  return response.data as { success: boolean; message: string };
}

export async function changeUserPassword(userId: number, password: string) {
  const response = await api.put(`/api/v1/auth/users/${userId}/password`, { password });
  return response.data as { success: boolean; message: string };
}

export async function resetUserPassword(userId: number) {
  const response = await api.post(`/api/v1/auth/users/${userId}/reset-password`);
  return response.data as { success: boolean; message: string; default_password: string };
}

export async function toggleUserEnabled(userId: number, enabled: boolean) {
  const response = await api.put(`/api/v1/auth/users/${userId}/enabled`, { enabled });
  return response.data as { success: boolean; message: string; enabled: boolean };
}

export async function updateUserNickname(userId: number, nickname: string) {
  const response = await api.put(`/api/v1/auth/users/${userId}/nickname`, { nickname });
  return response.data as { success: boolean; message: string };
}
