export class HttpClient {
    base;
    interceptors;
    constructor(base, interceptors = []) {
        this.base = base;
        this.interceptors = interceptors;
    }
    async send(schema, req) {
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
        const json = await response.json();
        return schema.parse(json);
    }
    async applyInterceptors(req) {
        let current = req;
        for (const apply of this.interceptors) {
            current = await apply(current);
        }
        return current;
    }
}
export class HttpError extends Error {
    status;
    bodyText;
    constructor(status, bodyText) {
        super(`HTTP ${String(status)}: ${bodyText.slice(0, 200)}`);
        this.status = status;
        this.bodyText = bodyText;
    }
}
async function safeText(response) {
    try {
        return await response.text();
    }
    catch {
        return "";
    }
}
