import { DatePicker, InputNumber, Radio, Space, Typography } from "antd";
import type { Dayjs } from "dayjs";
import { computeDateFromDays, computeDaysFromDate, type ExpiryMode } from "../utils/expiry";

type Props = {
  mode: ExpiryMode;
  onModeChange: (mode: ExpiryMode) => void;
  durationDays?: number | null;
  onDurationDaysChange: (value?: number | null) => void;
  targetDate?: Dayjs | null;
  onTargetDateChange: (value: Dayjs | null) => void;
  baseDate?: Dayjs | null;
  baseDateLabel?: string;
  baseDateText?: string;
  previewLabel?: string;
  allowNegativeDays?: boolean;
  zeroDaysText?: string;
};

export default function ExpiryModeField({
  mode,
  onModeChange,
  durationDays,
  onDurationDaysChange,
  targetDate,
  onTargetDateChange,
  baseDate,
  baseDateLabel = "计算基准",
  baseDateText,
  previewLabel = "计算结果",
  allowNegativeDays = true,
  zeroDaysText,
}: Props) {
  const previewDate = mode === "days" ? computeDateFromDays(durationDays ?? undefined, baseDate ?? undefined) : undefined;
  const previewDays = mode === "date" ? computeDaysFromDate(targetDate, baseDate ?? undefined) : undefined;

  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Radio.Group
        optionType="button"
        buttonStyle="solid"
        value={mode}
        onChange={(event) => onModeChange(event.target.value as ExpiryMode)}
        options={[
          { label: "按天数", value: "days" },
          { label: "选日期", value: "date" },
        ]}
      />

      {mode === "days" ? (
        <InputNumber
          style={{ width: "100%" }}
          placeholder={zeroDaysText || (allowNegativeDays ? "输入天数，可填负数" : "输入天数")}
          value={durationDays ?? null}
          onChange={(value) => onDurationDaysChange(typeof value === "number" ? value : undefined)}
        />
      ) : (
        <DatePicker
          style={{ width: "100%" }}
          value={targetDate ?? null}
          onChange={(value) => onTargetDateChange(value)}
          format="YYYY-MM-DD"
          allowClear
        />
      )}

      <Space direction="vertical" size={2}>
        {baseDateText ? <Typography.Text type="secondary">{baseDateLabel}：{baseDateText}</Typography.Text> : null}
        {mode === "days" ? (
          <Typography.Text type="secondary">{previewLabel}：{previewDate || "未计算"}</Typography.Text>
        ) : (
          <Typography.Text type="secondary">{previewLabel}：{targetDate ? `${targetDate.format("YYYY-MM-DD")}（相差 ${previewDays ?? 0} 天）` : "未选择"}</Typography.Text>
        )}
      </Space>
    </Space>
  );
}
