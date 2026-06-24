import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";

export default async function Home({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-surface-page px-6 py-16">
      <div className="flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-dark text-2xl font-bold text-white">
          م
        </div>
        <div>
          <div className="text-xl font-bold text-ink-950">{t("brand.name")}</div>
          <div className="text-xs tracking-wide text-muted">
            {t("brand.tagline")}
          </div>
        </div>
      </div>

      <div className="max-w-xl text-center">
        <h1 className="text-3xl font-semibold text-ink-950">
          {t("landing.headline")}
        </h1>
        <p className="mt-3 text-muted-soft">{t("landing.subhead")}</p>
      </div>

      <Link
        href="/dashboard"
        className="rounded-md bg-gradient-to-br from-brand to-brand-dark px-6 py-3 text-sm font-semibold text-white shadow-sm"
      >
        {t("landing.cta")}
      </Link>
    </main>
  );
}
