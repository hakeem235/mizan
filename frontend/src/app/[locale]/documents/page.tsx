"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { runOcr } from "@/lib/ocr";
import { createDocument, confirmDocument, type DocumentData } from "@/lib/api";

const EDITABLE = [
  "vendor",
  "invoice_number",
  "date",
  "vat_number",
  "subtotal",
  "vat_amount",
  "total",
] as const;

const sevBg: Record<string, string> = {
  danger: "bg-danger-bg text-danger-text",
  warning: "bg-warning-bg text-warning-text",
  info: "bg-success-tint text-success-text",
};

export default function DocumentsPage() {
  const t = useTranslations("documents");
  const [scanPct, setScanPct] = useState<number | null>(null);
  const [doc, setDoc] = useState<DocumentData | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [postedId, setPostedId] = useState<number | null>(null);
  const [error, setError] = useState(false);
  const [posting, setPosting] = useState(false);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(false);
    setDoc(null);
    setPostedId(null);
    try {
      setScanPct(0);
      const text = await runOcr(file, setScanPct);
      setScanPct(null);
      const created = await createDocument({
        filename: file.name,
        doc_type: "invoice",
        raw_text: text,
      });
      setDoc(created);
      const init: Record<string, string> = {};
      for (const k of EDITABLE) init[k] = created.extracted[k] ?? "";
      setFields(init);
    } catch {
      setScanPct(null);
      setError(true);
    }
  }

  async function handlePost() {
    if (!doc) return;
    setPosting(true);
    setError(false);
    try {
      const res = await confirmDocument(doc.id, { extracted: fields });
      setPostedId(res.journal_entry);
    } catch {
      setError(true);
    } finally {
      setPosting(false);
    }
  }

  return (
    <main className="min-h-screen bg-surface-page p-6">
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-ink-950">{t("title")}</h1>
        <p className="text-xs text-muted">{t("subtitle")}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        {/* Upload */}
        <div>
          <label className="block cursor-pointer rounded-lg border-2 border-dashed border-line bg-surface p-7 text-center hover:border-brand">
            <div className="text-[13px] font-semibold text-ink">{t("drop")}</div>
            <div className="mt-1 text-[11px] text-muted-faint">{t("docTypes")}</div>
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleFile}
            />
          </label>
          {scanPct !== null && (
            <div className="mt-3 text-[12px] text-muted">
              {t("scanning", { pct: scanPct })}
            </div>
          )}
        </div>

        {/* Extraction panel */}
        <div className="overflow-hidden rounded-lg border border-line bg-surface">
          <div className="flex items-center justify-between border-b border-line-soft px-5 py-4">
            <div className="text-sm font-semibold text-ink">{t("extracted")}</div>
            {doc && (
              <div className="text-[11.5px] text-muted">
                {t("confidence")}:{" "}
                <span className="num font-semibold">
                  {Math.round(Number(doc.confidence) * 100)}%
                </span>
              </div>
            )}
          </div>

          {!doc && (
            <div className="p-8 text-[13px] text-muted-faint">{t("drop")}</div>
          )}

          {doc && (
            <div className="p-5">
              <div className="grid gap-3 sm:grid-cols-2">
                {EDITABLE.map((k) => (
                  <div key={k}>
                    <label className="mb-1 block text-[11px] text-muted-faint">
                      {t(`fields.${k}`)}
                    </label>
                    <input
                      value={fields[k] ?? ""}
                      onChange={(ev) =>
                        setFields((f) => ({ ...f, [k]: ev.target.value }))
                      }
                      className="num w-full rounded-md border border-line px-3 py-2 text-[13px] font-medium text-ink outline-none focus:border-brand"
                    />
                  </div>
                ))}
              </div>

              {/* Inconsistency flags */}
              <div className="mt-5">
                <div className="mb-2 text-[12px] font-semibold text-ink">
                  {t("flagsTitle")}
                </div>
                {doc.flags.length === 0 ? (
                  <div className="rounded-md bg-success-bg px-3 py-2 text-[12px] text-success-text">
                    {t("noFlags")}
                  </div>
                ) : (
                  <ul className="flex flex-col gap-1.5">
                    {doc.flags.map((fl, i) => (
                      <li
                        key={i}
                        className={`rounded-md px-3 py-2 text-[12px] ${sevBg[fl.severity]}`}
                      >
                        {fl.message}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {postedId ? (
                <div className="mt-5 rounded-md bg-success-bg px-3 py-2.5 text-[13px] font-semibold text-success-text">
                  {t("posted", { id: postedId })}
                </div>
              ) : (
                <button
                  onClick={handlePost}
                  disabled={posting}
                  className="mt-5 w-full rounded-md bg-brand-dark py-2.5 text-[13px] font-semibold text-white disabled:opacity-60"
                >
                  {posting ? t("posting") : t("post")}
                </button>
              )}
            </div>
          )}

          {error && (
            <div className="px-5 pb-4 text-[12px] text-danger-text">{t("error")}</div>
          )}
        </div>
      </div>
    </main>
  );
}
