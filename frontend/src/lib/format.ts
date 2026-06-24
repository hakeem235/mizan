export function formatMoney(value: string | number, currency: string, locale: string) {
  const n = typeof value === "string" ? Number(value) : value;
  return new Intl.NumberFormat(locale === "ar" ? "ar-SA" : "en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
}
