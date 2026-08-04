"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { askAssistant, type AssistantAnswer } from "@/lib/api";

interface Turn {
  role: "user" | "ai";
  text: string;
  citations?: { label: string; value: string }[];
  disclaimer?: string;
}

export default function AssistantPage() {
  const t = useTranslations("assistant");
  const [turns, setTurns] = useState<Turn[]>([
    { role: "ai", text: t("intro") },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  const suggestionKeys = ["expenses", "invoices", "cashflow", "revenue"] as const;

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setInput("");
    setTurns((prev) => [...prev, { role: "user", text: q }]);
    setBusy(true);
    try {
      const res: AssistantAnswer = await askAssistant(q);
      setTurns((prev) => [
        ...prev,
        {
          role: "ai",
          text: res.answer,
          citations: res.grounded ? res.citations : undefined,
          disclaimer: res.grounded ? res.disclaimer : undefined,
        },
      ]);
    } catch {
      setTurns((prev) => [...prev, { role: "ai", text: t("error") }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col bg-surface-page p-6">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-ink-950">{t("title")}</h1>
        <p className="text-xs text-muted">{t("subtitle")}</p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto">
        {turns.map((turn, i) => (
          <div
            key={i}
            className={turn.role === "user" ? "flex justify-end" : "flex justify-start"}
          >
            <div
              className={
                turn.role === "user"
                  ? "max-w-[80%] rounded-lg bg-brand-dark px-4 py-2.5 text-[13px] text-white"
                  : "max-w-[85%] rounded-lg border border-line bg-surface px-4 py-3 text-[13px] text-ink"
              }
            >
              <div>{turn.text}</div>
              {turn.citations && turn.citations.length > 0 && (
                <div className="mt-3 border-t border-line-faint pt-2">
                  <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-muted-faint">
                    {t("citationsTitle")}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {turn.citations.map((c, j) => (
                      <span
                        key={j}
                        className="num rounded-pill bg-success-tint px-2 py-0.5 text-[11px] font-medium text-success-text"
                      >
                        {c.label}: {c.value}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {turn.disclaimer && (
                <div className="mt-2 text-[10.5px] italic text-muted-faint">
                  {turn.disclaimer}
                </div>
              )}
            </div>
          </div>
        ))}
        {busy && <div className="text-[12px] text-muted">{t("thinking")}</div>}
      </div>

      {/* Suggestions */}
      <div className="mt-4 flex flex-wrap gap-2">
        {suggestionKeys.map((k) => (
          <button
            key={k}
            onClick={() => ask(t(`suggestions.${k}`))}
            disabled={busy}
            className="rounded-pill border border-success-tint bg-success-tint px-3 py-1.5 text-[11.5px] font-medium text-success-text disabled:opacity-50"
          >
            {t(`suggestions.${k}`)}
          </button>
        ))}
      </div>

      {/* Input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="mt-3 flex items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("placeholder")}
          className="flex-1 bg-transparent text-[13px] text-ink outline-none"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-brand-dark px-4 py-1.5 text-[13px] font-semibold text-white disabled:opacity-50"
        >
          {t("send")}
        </button>
      </form>
    </main>
  );
}
