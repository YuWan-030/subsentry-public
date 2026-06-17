import { message } from "antd";
import type { MessageInstance } from "antd/es/message/interface";

let messageApi: MessageInstance | null = null;
let feedbackConfigured = false;

function ensureConfigured() {
  if (feedbackConfigured) {
    return;
  }
  message.config({
    top: 72,
    duration: 2,
    maxCount: 4,
  });
  feedbackConfigured = true;
}

function getMessageApi() {
  ensureConfigured();
  return messageApi ?? message;
}

export function bindFeedbackMessage(api: MessageInstance) {
  messageApi = api;
  ensureConfigured();
}

export function extractErrorMessage(error: any, fallback: string) {
  const value =
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.response?.data?.msg ||
    error?.message ||
    fallback;
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        const path = Array.isArray(item?.loc) ? item.loc.join(".") : "";
        return [path, item?.msg].filter(Boolean).join("：") || JSON.stringify(item);
      })
      .filter(Boolean)
      .join("；") || fallback;
  }
  if (value && typeof value === "object") {
    return value.msg || value.message || JSON.stringify(value);
  }
  return fallback;
}

export function notifyDataLoaded(key: string, text: string) {
  getMessageApi().success({
    key,
    content: text,
    duration: 1.2,
  });
}

export function notifyActionLoading(key: string, text: string) {
  getMessageApi().open({
    key,
    type: "loading",
    content: text,
    duration: 0,
  });
}

export function dismissActionFeedback(key: string) {
  getMessageApi().destroy(key);
}

export function notifyActionSuccess(key: string, text: string) {
  getMessageApi().success({
    key,
    content: text,
    duration: 1.6,
  });
}

export function notifyActionError(key: string, text: string) {
  getMessageApi().error({
    key,
    content: text,
    duration: 2.2,
  });
}

export function notifyActionWarning(key: string, text: string) {
  getMessageApi().warning({
    key,
    content: text,
    duration: 2,
  });
}
