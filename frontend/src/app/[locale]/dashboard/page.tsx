"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { getDashboard, type DashboardData } from "@/lib/api";
import { formatMoney } from "@/lib/format";

export default function DashboardPage() {
  const t = useTranslations("dashboard");
  const locale = useLocale();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getDashboard().then(setData).catch(() => setError(true));
  }, []);

  if (error) {
    return <div className="p-8 text-danger-text">{t("error")}</div>;
  }
  if (!data) {
    return <div className="p-8 text-muted">{t("loading")}</div>;
  }

  const { kpis, base_currency: cur, chart, health, recommendations } = data;
  const money = (v: string) => formatMoney(v, cur, locale);
  const kpiKeys = [
    "revenue",
    "expenses",
    "net_cash_flow",
    "outstanding_invoices",
    "vat_payable",
  ] as const;

  const maxBar = Math.max(
    1,
    ...chart.flatMap((c) => [Number(c.revenue), Number(c.expenses)]),
  );
  const sevColor: Record<string, string> = {
    danger: "#F04438",
    warning: "#E4A11B",
    info: "#34D8A8",
  };

  return (
    <main className="min-h-screen bg-surface-page p-6">
      {/* Header */}
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-ink-950">{t("title")}</h1>
        <p className="text-xs text-muted">
          {t("subtitle")} · {data.organization} · {data.period}
        </p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-3.5 md:grid-cols-5">
        {kpiKeys.map((k) => (
          <div
            key={k}
            className="animate-mz-rise rounded-lg border border-line bg-surface p-4"
          >
            <div className="text-[11.5px] font-medium text-muted">
              {t(`kpi.${k}`)}
            </div>
            <div className="num mt-2 text-xl font-semibold text-ink-950">
              {money(kpis[k])}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3.5 grid gap-3.5 lg:grid-cols-[1.7fr_1fr]">
        {/* Revenue vs Expenses chart */}
        <div className="rounded-lg border border-line bg-surface p-5">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-ink">{t("revVsExp")}</div>
              <div className="text-[11px] text-muted-faint">{t("last8")}</div>
            </div>
            <div className="flex gap-3.5 text-[11px] text-muted">
              <span className="flex items-center gap-1.5">
                <i className="inline-block h-2.5 w-2.5 rounded-sm bg-brand" />
                {t("revenue")}
              </span>
              <span className="flex items-center gap-1.5">
                <i className="inline-block h-2.5 w-2.5 rounded-sm bg-warning" />
                {t("expenses")}
              </span>
            </div>
          </div>
          <div className="flex h-44 items-end gap-3.5 pb-6">
            {chart.map((c) => (
              <div
                key={c.month}
                className="relative flex h-full flex-1 flex-col items-center justify-end gap-1.5"
              >
                <div className="flex h-full w-full items-end justify-center gap-1">
                  <div
                    className="w-3 rounded-t-sm bg-brand"
                    style={{ height: `${(Number(c.revenue) / maxBar) * 100}%` }}
                  />
                  <div
                    className="w-3 rounded-t-sm bg-warning"
                    style={{ height: `${(Number(c.expenses) / maxBar) * 100}%` }}
                  />
                </div>
                <span className="absolute -bottom-6 text-[10.5px] text-muted-faint">
                  {c.month}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Financial health */}
        <div className="flex flex-col rounded-lg border border-line bg-surface p-5">
          <div className="text-sm font-semibold text-ink">{t("health")}</div>
          <div className="flex flex-1 items-center justify-center py-3">
            <div
              className="flex h-36 w-36 items-center justify-center rounded-full"
              style={{
                background: `conic-gradient(#12A37E 0 ${health.score}%, #EAECF0 ${health.score}% 100%)`,
              }}
            >
              <div className="flex h-28 w-28 flex-col items-center justify-center rounded-full bg-surface">
                <span className="num text-3xl font-semibold text-ink-950">
                  {health.score}
                </span>
                <span className="text-[11px] font-semibold text-muted">
                  {health.label}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* AI recommendations + recent transactions */}
      <div className="mt-3.5 grid gap-3.5 lg:grid-cols-[1fr_1.4fr]">
        <div className="rounded-lg bg-gradient-to-br from-ink-900 to-ink-800 p-5 text-surface">
          <div className="mb-3.5 text-sm font-semibold text-white">
            {t("aiRecs")}
          </div>
          <div className="flex flex-col gap-2.5">
            {recommendations.map((r, i) => (
              <div
                key={i}
                className="rounded-md bg-white/5 p-3"
                style={{ borderInlineStart: `3px solid ${sevColor[r.severity]}` }}
              >
                <div className="mb-1 text-[12.5px] font-semibold text-white">
                  {r.title}
                </div>
                <div className="text-[11.5px] leading-relaxed text-[#9FB0C5]">
                  {r.body}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="overflow-hidden rounded-lg border border-line bg-surface">
          <div className="border-b border-line-soft px-5 py-3.5 text-sm font-semibold text-ink">
            {t("recentTxn")}
          </div>
          {data.recent_transactions.map((x) => (
            <div
              key={x.id}
              className="flex items-center gap-3 border-b border-line-faint px-5 py-2.5"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12.5px] font-medium text-ink">
                  {x.description}
                </div>
                <div className="text-[11px] text-muted-faint">{x.category}</div>
              </div>
              {x.is_duplicate && (
                <span className="rounded-pill bg-danger-bg px-2 py-0.5 text-[10.5px] font-semibold text-danger-text">
                  {t("duplicate")}
                </span>
              )}
              <div className="num text-[12.5px] font-semibold text-ink">
                {money(x.amount)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
