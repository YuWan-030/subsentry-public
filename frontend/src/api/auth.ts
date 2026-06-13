import { createContext, useContext } from "react";
import api from "./http";

export type CurrentUser = {
  username: string;
  nickname?: string;
  role: "admin" | "user";
  onauth_bound?: boolean;
  onauth_username?: string;
  onauth_bound_at?: string;
};

export type AuthContextValue = {
  user: CurrentUser | null;
  loading: boolean;
  refreshUser: () => Promise<CurrentUser | null>;
  logout: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthContext.Provider");
  }
  return value;
}

export async function updateMyProfile(payload: { nickname?: string }) {
  const response = await api.put("/api/v1/auth/me", payload);
  return response.data as {
    success: boolean;
    message: string;
    data: CurrentUser;
  };
}

export async function changeMyPassword(payload: { current_password: string; new_password: string }) {
  const response = await api.put("/api/v1/auth/me/password", payload);
  return response.data as {
    success: boolean;
    message: string;
  };
}

export async function fetchOnAuthConfig() {
  const response = await api.get("/api/v1/auth/onauth/config");
  return response.data.data as { enabled: boolean };
}

export async function startOnAuth(mode: "login" | "bind", redirectUri: string) {
  const response = await api.post("/api/v1/auth/onauth/start", { mode, redirect_uri: redirectUri });
  return response.data.data as { authorize_url: string };
}

export async function finishOnAuthCallback(payload: { code: string; state: string; redirect_uri: string }) {
  const response = await api.post("/api/v1/auth/onauth/callback", payload);
  return response.data as { success: boolean; message: string; data?: { mode: "login" | "bind"; onauth_username?: string } & Partial<CurrentUser> };
}

export async function unbindOnAuth() {
  const response = await api.delete("/api/v1/auth/onauth/binding");
  return response.data as { success: boolean; message: string };
}

export type PasskeyItem = {
  id: number;
  user_id: number;
  username: string;
  credential_id: string;
  label: string;
  device_type: string;
  backed_up: boolean | number;
  sign_count: number;
  created_at: string;
  last_used_at?: string | null;
};

export async function fetchPasskeys() {
  const response = await api.get("/api/v1/auth/passkeys");
  return response.data.data as { items: PasskeyItem[]; count: number };
}

export async function startPasskeyRegistration(origin: string) {
  const response = await api.post("/api/v1/auth/passkeys/register/start", { origin });
  return response.data.data as { challenge_id: string; options: PublicKeyCredentialCreationOptions };
}

export async function finishPasskeyRegistration(payload: { challenge_id: string; origin: string; credential: any; label?: string }) {
  const response = await api.post("/api/v1/auth/passkeys/register/complete", payload);
  return response.data as { success: boolean; message: string };
}

export async function startPasskeyAuthentication(origin: string, username?: string) {
  const response = await api.post("/api/v1/auth/passkeys/authenticate/start", { origin, username });
  return response.data.data as { challenge_id: string; options: PublicKeyCredentialRequestOptions };
}

export async function finishPasskeyAuthentication(payload: { challenge_id: string; origin: string; credential: any }) {
  const response = await api.post("/api/v1/auth/passkeys/authenticate/complete", payload);
  return response.data as { success: boolean; message: string; data: CurrentUser };
}

export async function deletePasskey(credentialId: number) {
  const response = await api.delete(`/api/v1/auth/passkeys/${credentialId}`);
  return response.data as { success: boolean; message: string };
}
