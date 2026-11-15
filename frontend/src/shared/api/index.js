import { HttpClient } from "./httpClient";
import { csrfInterceptor } from "./csrfInterceptor";
import { unauthorizedInterceptor } from "./unauthorizedInterceptor";
import { env } from "@/app/env";
export const httpClient = new HttpClient(env.apiBaseUrl, [
    csrfInterceptor,
    unauthorizedInterceptor,
]);
export { HttpError } from "./httpClient";
