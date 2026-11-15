import type { z } from "zod";

export interface HttpRequest {
  method: "GET" | "POST" | "PUT" | "DELETE";
  path: string;
  body?: unknown;
  headers?: Record<string, string>;
}

export type Interceptor = (req: HttpRequest) => HttpRequest | Promise<HttpRequest>;

export class HttpClient {
  private readonly base: string;
  private readonly interceptors: Interceptor[];

  constructor(base: string, interceptors: Interceptor[] = []) {
    this.base = base;
    this.interceptors = interceptors;
  }

  async send<T>(schema: z.ZodType<T>, req: HttpRequest): Promise<T> {
    const prepared = await this.applyInterceptors(req);
    const response = await fetch(`${this.base}${prepared.path}`, {
      method: prepared.method,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(prepared.headers ?? {}),
      },
      ...(prepared.body === undefined ? {} : { body: JSON.stringify(prepared.body) }),
    });
    if (!response.ok) {
      throw new HttpError(response.status, await safeText(response));
    }
    const json: unknown = await response.json();
    return schema.parse(json);
  }

  private async applyInterceptors(req: HttpRequest): Promise<HttpRequest> {
    let current = req;
    for (const apply of this.interceptors) {
      current = await apply(current);
    }
    return current;
  }
}

export class HttpError extends Error {
  constructor(readonly status: number, readonly bodyText: string) {
    super(`HTTP ${String(status)}: ${bodyText.slice(0, 200)}`);
  }
}

async function safeText(response: Response): Promise<string> {
  try {
    return await response.text();
  } catch {
    return "";
  }
}
