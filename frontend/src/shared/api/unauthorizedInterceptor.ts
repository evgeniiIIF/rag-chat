import type { Interceptor } from "./httpClient";

/**
 * rules/react.md: 401 -> refresh -> retry 1.
 * MVP без auth: интерсептор no-op, точка расширения.
 */
export const unauthorizedInterceptor: Interceptor = (req) => req;
