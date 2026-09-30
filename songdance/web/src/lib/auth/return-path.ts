const DESTINATION = /^(?:\/(?:zh|ja|ko|es|pt-br|fr|de))?(?:\/(?:transcribe|account)|\/jobs\/[A-Za-z0-9_-]{1,128})?\/?$/;

export function safeReturnPath(value: unknown): string {
  if (typeof value !== "string" || value.length > 2048 || !value.startsWith("/")) return "/account";
  try {
    const decoded = decodeURIComponent(value);
    if (decoded.startsWith("//") || /[\\\u0000-\u0020]/.test(decoded)) return "/account";
    const url = new URL(value, "https://return.invalid");
    if (url.origin !== "https://return.invalid" || !DESTINATION.test(url.pathname)) return "/account";
    return url.pathname + url.search + url.hash;
  } catch { return "/account"; }
}
