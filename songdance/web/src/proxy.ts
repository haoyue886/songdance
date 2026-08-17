import { type NextRequest, NextResponse } from "next/server";
import { localeFromPathname, stripLocalePrefix } from "@/i18n/routing";

const STABLE_ROUTE = /^(?:\/(?:zh|ja|ko|es|pt-br|fr|de))?(?:\/(?:transcribe|examples|privacy|terms))?\/?$/;
const JOB_ROUTE = /^(?:\/(?:zh|ja|ko|es|pt-br|fr|de))?\/jobs\/[^/]+\/?$/;

export default function proxy(request: NextRequest) {
  const locale = localeFromPathname(request.nextUrl.pathname);
  const externalPath = stripLocalePrefix(request.nextUrl.pathname);
  const rewriteUrl = request.nextUrl.clone();
  rewriteUrl.pathname = `/${locale}${externalPath}`;
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-next-intl-locale", locale);
  const isKnownRoute = STABLE_ROUTE.test(request.nextUrl.pathname) || JOB_ROUTE.test(request.nextUrl.pathname);
  const response = NextResponse.rewrite(rewriteUrl, {
    status: isKnownRoute ? undefined : 404,
    request: { headers: requestHeaders },
  });
  response.cookies.set("NEXT_LOCALE", locale, {
    path: "/",
    sameSite: "lax",
  });
  return response;
}

export const config = {
  matcher: "/((?!api|_next|_vercel|(?:en|zh-CN)(?:/|$)|.*\\..*).*)",
};
