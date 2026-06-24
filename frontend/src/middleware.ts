import createIntlMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

// Scaffold: locale routing only. Auth (Clerk) middleware is layered in a later
// issue when the protected dashboard routes land.
export default createIntlMiddleware(routing);

export const config = {
  matcher: [
    "/((?!_next|_vercel|.*\\..*).*)",
  ],
};
