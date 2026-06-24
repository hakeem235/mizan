// Thin client for the Mizan Django API. The base URL is build/run-time config.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface DashboardKpis {
  revenue: string;
  expenses: string;
  net_cash_flow: string;
  outstanding_invoices: string;
  vat_payable: string;
}

export interface ChartPoint {
  month: string;
  revenue: string;
  expenses: string;
}

export interface Recommendation {
  title: string;
  body: string;
  severity: "danger" | "warning" | "info";
}

export interface RecentTransaction {
  id: number;
  description: string;
  category: string;
  amount: string;
  is_duplicate: boolean;
}

export interface DashboardData {
  organization: string;
  period: string;
  base_currency: string;
  kpis: DashboardKpis;
  health: { score: number; label: string };
  recommendations: Recommendation[];
  chart: ChartPoint[];
  recent_transactions: RecentTransaction[];
}

export function getDashboard() {
  return apiGet<DashboardData>("/api/dashboard/");
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface DocFlag {
  field: string;
  message: string;
  severity: "danger" | "warning" | "info";
}

export interface DocumentData {
  id: number;
  filename: string;
  doc_type: string;
  status: string;
  extracted: Record<string, string | null>;
  flags: DocFlag[];
  confidence: string;
  journal_entry: number | null;
}

export function createDocument(input: {
  filename: string;
  doc_type: string;
  raw_text: string;
}) {
  return apiPost<DocumentData>("/api/documents/", input);
}

export function confirmDocument(
  id: number,
  body: { extracted?: Record<string, string>; expense_account?: number } = {},
) {
  return apiPost<{ document: DocumentData; journal_entry: number }>(
    `/api/documents/${id}/confirm/`,
    body,
  );
}

export interface Citation {
  label: string;
  value: string;
}

export interface AssistantAnswer {
  intent: string | null;
  answer: string;
  grounded: boolean;
  citations: Citation[];
  disclaimer: string;
}

export function askAssistant(question: string) {
  return apiPost<AssistantAnswer>("/api/assistant/ask/", { question });
}

export interface ReportColumn {
  label: string;
  numeric: boolean;
}

export interface ReportRow {
  cells: (string | null)[];
  style: "normal" | "section" | "subtotal" | "total";
}

export interface Report {
  key: string;
  title: string;
  subtitle: string;
  columns: ReportColumn[];
  rows: ReportRow[];
  meta: Record<string, unknown>;
}

export function getReport(key: string) {
  return apiGet<Report>(`/api/reports/${key}/`);
}

// Direct download URL for a report export (xlsx | pdf).
export function reportExportUrl(key: string, fmt: "xlsx" | "pdf") {
  return `${API_BASE_URL}/api/reports/${key}/?export=${fmt}`;
}
