import createMiddleware from "next-intl/middleware";
import { type NextRequest, NextResponse } from "next/server";
import { routing } from "./i18n/routing";

const handleI18nRouting = createMiddleware(routing);
const STABLE_ROUTE = /^(?:\/zh)?(?:\/(?:transcribe|examples|privacy|terms))?\/?$/;
const JOB_ROUTE = /^(?:\/zh)?\/jobs\/[^/]+\/?$/;

export default function proxy(request: NextRequest) {
  const response = handleI18nRouting(request);
  if (STABLE_ROUTE.test(request.nextUrl.pathname) || JOB_ROUTE.test(request.nextUrl.pathname))
    return response;

  const isChinese = request.nextUrl.pathname === "/zh" || request.nextUrl.pathname.startsWith("/zh/");
  const externalPath = isChinese ? request.nextUrl.pathname.replace(/^\/zh/, "") || "/" : request.nextUrl.pathname;
  const rewriteUrl = request.nextUrl.clone();
  rewriteUrl.pathname = `/${isChinese ? "zh-CN" : "en"}${externalPath}`;
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-next-intl-locale", isChinese ? "zh-CN" : "en");
  return NextResponse.rewrite(rewriteUrl, {
    status: 404,
    request: { headers: requestHeaders },
  });
}

export const config = {
  matcher: "/((?!api|_next|_vercel|.*\\..*).*)",
};
