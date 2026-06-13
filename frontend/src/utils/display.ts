export function formatIpLimit(value?: number | null) {
  const numericValue = Number(value ?? 0);
  return numericValue > 0 ? String(numericValue) : "不限制";
}

export function formatDateTimeText(value?: string | null) {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  return raw.replace("T", " ").replace(/\.\d+$/, "").replace(/([+-]\d{2}:\d{2}|Z)$/, "");
}

export function formatDisplayValue(key: string, value: unknown): unknown {
  if (key === "limit_ip" || key === "limitIp" || key === "IP 限制") {
    return formatIpLimit(typeof value === "number" ? value : Number(value || 0));
  }
  return value;
}

export function formatJsonForDisplay(content?: string) {
  if (!content) {
    return "暂无详情";
  }

  try {
    const parsed = JSON.parse(content);
    return JSON.stringify(formatObjectForDisplay(parsed), null, 2);
  } catch {
    return content.replace(/("?(?:limit_ip|limitIp)"?\s*:\s*)0\b/g, "$1\"不限制\"");
  }
}

function formatObjectForDisplay(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(formatObjectForDisplay);
  }
  if (!value || typeof value !== "object") {
    return value;
  }

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      formatDisplayValue(key, formatObjectForDisplay(item)),
    ]),
  );
}
