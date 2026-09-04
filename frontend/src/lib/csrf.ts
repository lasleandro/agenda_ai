/**
 * Double-submit CSRF: echo the non-HttpOnly `agenda_csrf_token` cookie that
 * the backend sets on login/impersonate into an `X-CSRF-Token` header for
 * unsafe requests. The backend only enforces this in production, but the
 * header is harmless to send everywhere.
 */

const CSRF_COOKIE_NAME = "agenda_csrf_token";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"]);

function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${CSRF_COOKIE_NAME}=`));
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE_NAME.length + 1)) : null;
}

export function csrfHeaders(method: string = "GET"): Record<string, string> {
  if (SAFE_METHODS.has(method.toUpperCase())) return {};
  const token = readCsrfCookie();
  return token ? { "X-CSRF-Token": token } : {};
}
