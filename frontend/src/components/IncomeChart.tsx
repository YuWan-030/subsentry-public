import { useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts";
import type { MonthlyIncomeItem } from "../api/dashboard";
import { useTheme } from "../theme/ThemeProvider";

type Props = {
  series: MonthlyIncomeItem[];
};

const formatCurrency = (value: number) =>
  new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);

export default function IncomeChart({ series }: Props) {
  const { theme } = useTheme();
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.EChartsType | null>(null);
  const resizeFrameRef = useRef<number | null>(null);

  const option = useMemo(
    () => {
      const isSweetPink = theme === "sweetpink";
      const lineColor = isSweetPink ? "#e68fb0" : "#0a84ff";
      const axisColor = isSweetPink ? "#b2879a" : "#64748b";
      const gridColor = isSweetPink ? "rgba(230, 143, 176, 0.18)" : "rgba(148,163,184,0.2)";
      const axisLineColor = isSweetPink ? "rgba(224, 174, 194, 0.34)" : "rgba(148,163,184,0.35)";

      return ({
      backgroundColor: "transparent",
      tooltip: {
        trigger: "axis",
        backgroundColor: isSweetPink ? "rgba(109, 84, 98, 0.92)" : "rgba(17,24,39,0.92)",
        borderColor: isSweetPink ? "rgba(255, 225, 235, 0.5)" : "transparent",
        borderWidth: isSweetPink ? 1 : 0,
        textStyle: { color: "#fff" },
        valueFormatter: (value: number | string) => formatCurrency(Number(value || 0)),
      },
      grid: { top: 18, left: 6, right: 12, bottom: 4, containLabel: true },
      xAxis: {
        type: "category",
        data: series.map((item) => item.month),
        axisLine: { lineStyle: { color: axisLineColor } },
        axisTick: { show: false },
        axisLabel: { color: axisColor },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { type: "dashed", color: gridColor } },
        axisLabel: {
          color: axisColor,
          formatter: (value: number) => formatCurrency(value),
        },
      },
      series: [
        {
          data: series.map((item) => item.income),
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 3, color: lineColor },
          itemStyle: { color: lineColor },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: isSweetPink ? "rgba(230,143,176,0.26)" : "rgba(10,132,255,0.25)" },
              { offset: 1, color: isSweetPink ? "rgba(230,143,176,0.04)" : "rgba(10,132,255,0.02)" },
            ]),
          },
        },
      ],
    });
    },
    [series, theme]
  );

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current = echarts.init(ref.current);

    const resize = () => {
      if (resizeFrameRef.current !== null) {
        window.cancelAnimationFrame(resizeFrameRef.current);
      }
      resizeFrameRef.current = window.requestAnimationFrame(() => {
        resizeFrameRef.current = null;
        chartRef.current?.resize();
      });
    };

    const resizeObserver = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(resize);
    resizeObserver?.observe(ref.current);

    window.addEventListener("resize", resize);
    window.addEventListener("orientationchange", resize);

    const timers = [80, 240, 600, 1200].map((delay) => window.setTimeout(resize, delay));

    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
      if (resizeFrameRef.current !== null) {
        window.cancelAnimationFrame(resizeFrameRef.current);
        resizeFrameRef.current = null;
      }
      resizeObserver?.disconnect();
      window.removeEventListener("resize", resize);
      window.removeEventListener("orientationchange", resize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
    chartRef.current?.resize();
  }, [option]);

  return <div ref={ref} style={{ width: "100%", height: 320 }} />;
}

