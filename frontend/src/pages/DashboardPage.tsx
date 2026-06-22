import { useEffect, useRef, useState } from "react";
import { Button, Card, Col, Grid, Row, Segmented, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { DashboardOutlined, SyncOutlined } from "@ant-design/icons";
import { fetchDashboardIncome, fetchDashboardStatus, fetchMonthlyIncome, type DashboardPeriod, type DashboardSummary, type MonthlyIncomeItem } from "../api/dashboard";
import { fetchSiteConfig, type SiteConfig } from "../api/settings";
import AnnouncementBanner from "../components/AnnouncementBanner";
import IncomeChart from "../components/IncomeChart";
import { extractErrorMessage, notifyActionError, notifyDataLoaded } from "../utils/feedback";

const { useBreakpoint } = Grid;

const formatNumber = (num: number) => new Intl.NumberFormat("zh-CN").format(num);
const formatCurrency = (num: number) => new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(num);

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [series, setSeries] = useState<MonthlyIncomeItem[]>([]);
  const [siteConfig, setSiteConfig] = useState<SiteConfig | null>(null);
  const [period, setPeriod] = useState<DashboardPeriod>("month");
  const [statusLoading, setStatusLoading] = useState(false);
  const [incomeTotalLoading, setIncomeTotalLoading] = useState(false);
  const [incomeLoading, setIncomeLoading] = useState(false);
  const summaryLoadedRef = useRef(false);
  const statusRequestRef = useRef(0);
  const incomeTotalRequestRef = useRef(0);
  const incomeRequestRef = useRef(0);
  const initialIncomeTimerRef = useRef<number | null>(null);
  const initialSafariRetryRef = useRef<number | null>(null);
  const firstLoadRef = useRef(true);
  const screens = useBreakpoint();
  const isMobile = screens.md === false;
  const isCompactDesktop = !isMobile && screens.xl === false;
  const periodLabelMap: Record<DashboardPeriod, string> = {
    today: "今日",
    week: "本周",
    month: "本月",
  };
  const periodLabel = periodLabelMap[period];

  const loadStatus = async (force = false, showSuccess = false) => {
    const requestId = ++statusRequestRef.current;
    setStatusLoading(true);
    try {
      const statusData = await fetchDashboardStatus(force);
      if (requestId !== statusRequestRef.current) {
        return;
      }
      summaryLoadedRef.current = true;
      setSummary((current) => ({ ...(current || { month_income: 0 }), ...statusData }));
      if (showSuccess) {
        notifyDataLoaded("dashboard-refresh", "看板数据已刷新");
      }
    } catch (error: any) {
      notifyActionError("dashboard-refresh", extractErrorMessage(error, "看板数据加载失败"));
    } finally {
      if (requestId !== statusRequestRef.current) {
        return;
      }
      setStatusLoading(false);
    }
  };

  const loadIncomeTotal = async (periodValue: DashboardPeriod, force = false) => {
    const requestId = ++incomeTotalRequestRef.current;
    setIncomeTotalLoading(true);
    try {
      const monthIncome = await fetchDashboardIncome(periodValue, force);
      if (requestId !== incomeTotalRequestRef.current) {
        return;
      }
      setSummary((current) => ({
        total_count: current?.total_count ?? 0,
        healthy_count: current?.healthy_count ?? 0,
        disabled_count: current?.disabled_count ?? 0,
        expired_count: current?.expired_count ?? 0,
        warning_count: current?.warning_count ?? 0,
        month_income: monthIncome,
      }));
    } catch (error: any) {
      notifyActionError("dashboard-income", extractErrorMessage(error, "收入数据加载失败"));
    } finally {
      if (requestId !== incomeTotalRequestRef.current) {
        return;
      }
      setIncomeTotalLoading(false);
    }
  };

  const loadSecondaryData = async (periodValue: DashboardPeriod, force = false) => {
    const requestId = ++incomeRequestRef.current;
    setIncomeLoading(true);
    try {
      const incomeData = await fetchMonthlyIncome(periodValue, force);
      if (requestId !== incomeRequestRef.current) {
        return;
      }
      setSeries(incomeData);
    } catch (error: any) {
      notifyActionError("dashboard-secondary", extractErrorMessage(error, "看板辅助数据加载失败"));
    } finally {
      if (requestId !== incomeRequestRef.current) {
        return;
      }
      setIncomeLoading(false);
    }
  };

  const refreshAll = async (showSuccess = false) => {
    summaryLoadedRef.current = false;
    await Promise.all([loadStatus(true, showSuccess), loadIncomeTotal(period, true), loadSecondaryData(period, true)]);
  };

  useEffect(() => {
    void fetchSiteConfig()
      .then((config) => {
        setSiteConfig(config);
      })
      .catch(() => {
        setSiteConfig(null);
      });
  }, []);

  useEffect(() => {
    summaryLoadedRef.current = false;
    if (firstLoadRef.current) {
      void loadStatus();
      void loadIncomeTotal(period);
      initialIncomeTimerRef.current = window.setTimeout(() => {
        void loadSecondaryData(period);
      }, 350);
      initialSafariRetryRef.current = window.setTimeout(() => {
        if (!summaryLoadedRef.current) {
          void loadStatus();
        }
      }, 4000);
      firstLoadRef.current = false;
      return () => {
        if (initialIncomeTimerRef.current !== null) {
          window.clearTimeout(initialIncomeTimerRef.current);
          initialIncomeTimerRef.current = null;
        }
        if (initialSafariRetryRef.current !== null) {
          window.clearTimeout(initialSafariRetryRef.current);
          initialSafariRetryRef.current = null;
        }
      };
    }
    void loadIncomeTotal(period);
    void loadSecondaryData(period);
    return () => {
      if (initialIncomeTimerRef.current !== null) {
        window.clearTimeout(initialIncomeTimerRef.current);
        initialIncomeTimerRef.current = null;
      }
      if (initialSafariRetryRef.current !== null) {
        window.clearTimeout(initialSafariRetryRef.current);
        initialSafariRetryRef.current = null;
      }
    };
  }, [period]);

  const incomeColumns: ColumnsType<MonthlyIncomeItem> = [
    {
      title: "统计月份",
      dataIndex: "month",
      key: "month",
      render: (text: string) => <span style={{ fontWeight: 500, color: "var(--text-main)" }}>{text}</span>,
    },
    {
      title: "营收预测流水",
      dataIndex: "income",
      key: "income",
      align: "right",
      render: (value: number) => (
        <span style={{ fontFamily: "SF Pro Display, -apple-system", fontWeight: 600, color: "var(--text-main)" }}>
          {formatCurrency(value)}
        </span>
      ),
    },
  ];

  return (
    <div style={{ minWidth: 0, overflowX: "hidden" }}>
      <style>{`
        .apple-fluid-card {
          background: var(--glass-bg) !important;
          border: 1px solid var(--glass-border) !important;
          border-radius: ${isMobile ? "14px" : "20px"} !important;
          box-shadow: var(--shadow-main) !important;
          overflow: hidden;
        }
        .apple-stat-label {
          font-size: ${isMobile ? "12px" : "13px"};
          font-weight: 500;
          color: var(--text-sub);
        }
        .apple-stat-val {
          font-size: ${isMobile ? "22px" : "32px"} !important;
          font-weight: 700 !important;
          letter-spacing: 0;
          color: var(--text-main) !important;
          margin-top: 4px;
          text-overflow: ellipsis;
          overflow: hidden;
          white-space: nowrap;
        }
        .apple-stat-indicator {
          height: 3px;
          width: 36px;
          border-radius: 10px;
          margin: 12px auto 0 auto;
        }
      `}</style>

      <AnnouncementBanner config={siteConfig} />

      <div style={{ display: "flex", flexDirection: isMobile ? "column" : "row", justifyContent: "space-between", alignItems: isMobile ? "stretch" : "center", gap: 16, marginBottom: 24 }}>
        <div>
          <Space align="center" size={8}>
            <DashboardOutlined style={{ color: "var(--apple-blue)", fontSize: 18 }} />
            <Typography.Title level={isMobile ? 4 : 3} style={{ margin: 0, fontWeight: 700 }}>资产总览</Typography.Title>
          </Space>
          <Typography.Paragraph style={{ margin: "4px 0 0 0", color: "var(--text-sub)", fontSize: 13 }}>
            高层决策看板聚合客户资产、临期风险和月度收入走势。
          </Typography.Paragraph>
        </div>
        <div style={{ display: "flex", gap: 8, width: isMobile ? "100%" : "auto" }}>
          <Segmented
            options={[
              { label: "今日", value: "today" },
              { label: "本周", value: "week" },
              { label: "本月", value: "month" },
            ]}
            value={period}
            onChange={(value) => setPeriod(value as DashboardPeriod)}
            block={isMobile}
            style={{ background: "var(--surface-soft)" }}
          />
          <Button icon={<SyncOutlined />} loading={statusLoading || incomeTotalLoading || incomeLoading} onClick={() => void refreshAll(true)} style={{ borderRadius: 8 }} />
        </div>
      </div>

      <Row gutter={isMobile ? [10, 10] : [16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={12} lg={isCompactDesktop ? 12 : 6}>
          <Card bordered={false} className="apple-fluid-card" bodyStyle={{ padding: isMobile ? 12 : 20, textAlign: "center" }}>
            <div className="apple-stat-label">总客户资产数量</div>
            <div className="apple-stat-val">{statusLoading ? "..." : formatNumber(summary?.total_count ?? 0)}</div>
            <div className="apple-stat-indicator" style={{ backgroundColor: "var(--apple-blue)" }} />
          </Card>
        </Col>
        <Col xs={12} lg={isCompactDesktop ? 12 : 6}>
          <Card bordered={false} className="apple-fluid-card" bodyStyle={{ padding: isMobile ? 12 : 20, textAlign: "center" }}>
            <div className="apple-stat-label">正常运行服务中</div>
            <div className="apple-stat-val" style={{ color: "var(--status-success)" }}>
              {statusLoading ? "..." : formatNumber(summary?.healthy_count ?? 0)}
            </div>
            <div className="apple-stat-indicator" style={{ backgroundColor: "var(--status-success)" }} />
          </Card>
        </Col>
        <Col xs={12} lg={isCompactDesktop ? 12 : 6}>
          <Card bordered={false} className="apple-fluid-card" bodyStyle={{ padding: isMobile ? 12 : 20, textAlign: "center" }}>
            <div className="apple-stat-label">7天内到期临期</div>
            <div className="apple-stat-val" style={{ color: "var(--status-warning)" }}>{statusLoading ? "..." : formatNumber(summary?.warning_count ?? 0)}</div>
            <div className="apple-stat-indicator" style={{ backgroundColor: "var(--status-warning)" }} />
          </Card>
        </Col>
        <Col xs={12} lg={isCompactDesktop ? 12 : 6}>
          <Card bordered={false} className="apple-fluid-card" bodyStyle={{ padding: isMobile ? 12 : 20, textAlign: "center" }}>
            <div className="apple-stat-label">{periodLabel}营收流水预测</div>
            <div className="apple-stat-val" style={{ color: "var(--status-danger)", fontSize: isMobile ? "16px" : "26px" }}>
              {incomeTotalLoading ? "..." : formatCurrency(summary?.month_income ?? 0)}
            </div>
            <div className="apple-stat-indicator" style={{ backgroundColor: "var(--status-danger)" }} />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ alignItems: "stretch", marginBottom: 20 }}>
        <Col xs={24}>
          <Card
            title={<span style={{ fontWeight: 600, color: "var(--text-main)", fontSize: 14 }}>{periodLabel}收入趋势走势曲线</span>}
            bordered={false}
            className="apple-fluid-card"
            bodyStyle={{ padding: isMobile ? 12 : 20 }}
          >
            <div style={{ minHeight: isMobile ? 240 : 300, display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <IncomeChart series={series} />
            </div>
          </Card>
        </Col>
      </Row>

      <Card
        title={<span style={{ fontWeight: 600, color: "var(--text-main)", fontSize: 14 }}>{periodLabel}收入明细流水</span>}
        className="apple-fluid-card"
        bordered={false}
        bodyStyle={{ padding: isMobile ? "4px 8px" : "8px 16px" }}
      >
        <Table rowKey="month" size={isMobile || isCompactDesktop ? "small" : "middle"} loading={incomeLoading} pagination={false} columns={incomeColumns} dataSource={series} scroll={isMobile ? { x: 520 } : undefined} />
      </Card>
    </div>
  );
}
