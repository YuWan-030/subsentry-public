import api from "./http";
import type { CurrentUser } from "./auth";

export type InstallStatus = {
  required: boolean;
  completed: boolean;
  admin_count: number;
  database: {
    type: "sqlite" | "mysql";
    sqlite_file?: string;
    mysql?: {
      host: string;
      port: number;
      user: string;
      database: string;
    };
  };
  site_url: string;
  webhook_configured: boolean;
};

export type InstallDatabasePayload = {
  db_type: "sqlite" | "mysql";
  sqlite_file?: string;
  mysql_host?: string;
  mysql_port?: number;
  mysql_user?: string;
  mysql_password?: string;
  mysql_database?: string;
};

export type InstallCompletePayload = {
  admin_username: string;
  admin_password: string;
  admin_nickname?: string;
  site_url?: string;
  webhook_url?: string;
};

export async function fetchInstallStatus(): Promise<InstallStatus> {
  const response = await api.get("/api/v1/install/status");
  return response.data.data as InstallStatus;
}

export async function testInstallDatabase(payload: InstallDatabasePayload) {
  const response = await api.post("/api/v1/install/database/test", payload);
  return response.data as { success: boolean; message: string };
}

export async function saveInstallDatabase(payload: InstallDatabasePayload) {
  const response = await api.post("/api/v1/install/database", payload);
  return response.data as { success: boolean; message: string; restart_required: boolean; database: InstallStatus["database"] };
}

export async function completeInstall(payload: InstallCompletePayload) {
  const response = await api.post("/api/v1/install/complete", payload);
  return response.data as { success: boolean; message: string; data: CurrentUser };
}
