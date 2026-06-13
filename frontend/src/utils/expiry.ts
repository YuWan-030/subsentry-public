import dayjs, { type Dayjs } from "dayjs";

export type ExpiryMode = "days" | "date";

export const DEFAULT_EXPIRY_MODE: ExpiryMode = "days";

export function getTodayBase(): Dayjs {
  return dayjs().startOf("day");
}

export function parseDateValue(value?: string | null): Dayjs | null {
  if (!value) {
    return null;
  }
  const parsed = dayjs(value, "YYYY-MM-DD", true);
  return parsed.isValid() ? parsed.startOf("day") : null;
}

export function formatDateValue(value?: Dayjs | null): string | undefined {
  if (!value || !value.isValid()) {
    return undefined;
  }
  return value.startOf("day").format("YYYY-MM-DD");
}

export function computeDateFromDays(days?: number | null, baseDate?: Dayjs | null): string | undefined {
  if (days === undefined || days === null || Number.isNaN(days)) {
    return undefined;
  }
  if (days === 0) {
    return "无限期";
  }
  return (baseDate || getTodayBase()).add(days, "day").format("YYYY-MM-DD");
}

export function computeDaysFromDate(targetDate?: Dayjs | null, baseDate?: Dayjs | null): number | undefined {
  if (!targetDate || !targetDate.isValid()) {
    return undefined;
  }
  return targetDate.startOf("day").diff((baseDate || getTodayBase()).startOf("day"), "day");
}

export function getRenewBaseDate(currentExpiry?: string | null, isUnlimited?: boolean): Dayjs {
  const today = getTodayBase();
  if (isUnlimited) {
    return today;
  }
  const expiry = parseDateValue(currentExpiry);
  if (!expiry) {
    return today;
  }
  return expiry.isBefore(today) ? today : expiry;
}

export function buildExpiryPayload(mode: ExpiryMode, durationDays?: number | null, targetDate?: Dayjs | null) {
  if (mode === "date") {
    return {
      duration_mode: "date" as const,
      custom_expiry_date: formatDateValue(targetDate),
    };
  }
  return {
    duration_mode: "days" as const,
    duration_days: durationDays ?? undefined,
  };
}
