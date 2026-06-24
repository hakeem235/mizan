import type { ReactNode } from "react";
import "./globals.css";

// Root layout is intentionally a pass-through: the localized <html> (with the
// correct lang/dir) is rendered by src/app/[locale]/layout.tsx.
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
