"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { getReport, reportExportUrl, type Report } from "@/lib/api";

const REPORT_KEYS = [
  "trial_balance",
  "profit_and_loss",
  "balance_sheet",
  "cash_flow",
  "general_ledger",
  "ar_aging",
  "ap_aging",
  "vat_report",
] as const;

const ROW_CLASS: Record<string, string> = {
  section: "font-semibold text-ink bg-surface-subtle",
  subtotal: "font-semibold text-ink",
  total: "font-semibold text-ink-950 border-t-2 border-line",
  normal: "text-muted-soft",
};

export default function ReportsPage() {
  const t = useTranslations("reports");
  const [active, setActive] = useState<string>(REPORT_KEYS[0]);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    setReport(null);
    setError(false);
    getReport(active).then(setReport).catch(() => setError(true));
  }, [active]);

  return (
    <main className="min-h-screen bg-surface-page p-6">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink-950">{t("title")}</h1>
          <p className="text-xs text-muted">{t("subtitle")}</p>
        </div>
        <div className="flex gap-2">
          <a
            href={reportExportUrl(active, "pdf")}
            className="flex items-center gap-1.5 rounded-md border border-line bg-surface px-3 py-2 text-[12px] font-semibold text-muted-strong"
          >
            <span className="text-danger-text">▦</span> {t("exportPdf")}
          </a>
          <a
            href={reportExportUrl(active, "xlsx")}
            className="flex items-center gap-1.5 rounded-md border border-line bg-surface px-3 py-2 text-[12px] font-semibold text-muted-strong"
          >
            <span className="text-success-text">▦</span> {t("exportExcel")}
          </a>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-4 flex flex-wrap gap-2">
        {REPORT_KEYS.map((k) => (
          <button
            key={k}
            onClick={() => setActive(k)}
            className={
              "rounded-md px-3 py-1.5 text-[12px] font-semibold " +
              (active === k
                ? "bg-brand-dark text-white"
                : "border border-line bg-surface text-muted-strong")
            }
          >
            {t(`tabs.${k}`)}
          </button>
        ))}
      </div>

      {/* Report */}
      <div className="overflow-hidden rounded-lg border border-line bg-surface">
        {error && <div className="p-6 text-[13px] text-danger-text">{t("error")}</div>}
        {!error && !report && (
          <div className="p-6 text-[13px] text-muted">{t("loading")}</div>
        )}
        {report && (
          <div>
            <div className="border-b border-line-soft px-5 py-4">
              <div className="text-[15px] font-semibold text-ink">{report.title}</div>
              <div className="text-[11.5px] text-muted-faint">{report.subtitle}</div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-[12.5px]">
                <thead>
                  <tr className="bg-surface-subtle text-muted">
                    {report.columns.map((c, i) => (
                      <th
                        key={i}
                        className={
                          "px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide " +
                          (c.numeric ? "text-end" : "text-start")
                        }
                      >
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {report.rows.map((row, ri) => (
                    <tr
                      key={ri}
                      className={"border-t border-line-faint " + (ROW_CLASS[row.style] ?? "")}
                    >
                      {row.cells.map((cell, ci) => (
                        <td
                          key={ci}
                          className={
                            "px-4 py-2 " +
                            (report.columns[ci]?.numeric ? "num text-end" : "text-start")
                          }
                        >
                          {report.columns[ci]?.numeric
                            ? cell === null
                              ? "-"
                              : Number(cell).toLocaleString(undefined, {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 2,
                                })
                            : cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
