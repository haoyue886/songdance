import createMiddleware from "next-intl/middleware";
import { type NextRequest, NextResponse } from "next/server";
import { localeFromPathname, routing } from "@/i18n/routing";

const handleI18nRouting = createMiddleware(routing);
const STABLE_ROUTE = /^(?:\/(?:zh|ja|ko|es|pt-br|fr|de))?(?:\/(?:transcribe|examples|privacy|terms))?\/?$/;
const JOB_ROUTE = /^(?:\/(?:zh|ja|ko|es|pt-br|fr|de))?\/jobs\/[^/]+\/?$/;

export default function proxy(request: NextRequest) {
  const response = handleI18nRouting(request);
  const isKnownRoute = STABLE_ROUTE.test(request.nextUrl.pathname) || JOB_ROUTE.test(request.nextUrl.pathname);
  if (isKnownRoute) return response;

  const locale = localeFromPathname(request.nextUrl.pathname);
  const rewriteUrl = new URL(`/en${request.nextUrl.pathname}${request.nextUrl.search}`, request.url);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-next-intl-locale", locale);
  const init = { status: 404, request: { headers: requestHeaders } };
  const notFoundResponse = locale === "en"
    ? NextResponse.rewrite(rewriteUrl, init)
    : NextResponse.next(init);
  notFoundResponse.cookies.set("NEXT_LOCALE", locale, { path: "/", sameSite: "lax" });
  return notFoundResponse;
}

export const config = {
  matcher: "/((?!api|_next|_vercel|en(?:/|$)|.*\\..*).*)",
};
