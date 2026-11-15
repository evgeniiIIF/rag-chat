import type { Interceptor } from "./httpClient";

const CSRF_COOKIE = "XSRF-TOKEN";

export const csrfInterceptor: Interceptor = (req) => {
  if (req.method === "GET") {
    return req;
  }
  const token = readCookie(CSRF_COOKIE);
  if (token === null) {
    return req;
  }
  return {
    ...req,
    headers: { ...(req.headers ?? {}), "X-CSRF-Token": token },
  };
};

function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return null;
}
