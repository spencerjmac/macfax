/**
 * Framework-agnostic API client factory.
 *
 * Pure TypeScript: no process.env, next/*, window/document, or React.
 * Each caller supplies the base URL and fetch options for its runtime
 * (see lib/api-env.ts for the Next.js web configuration).
 */

export type QueryValue = string | number | boolean | undefined | null;
export type QueryParams = Record<string, QueryValue>;

export type ErrorFormatter = (status: number, body: string) => string;

export interface ApiClientConfig {
  /**
   * Prefix every request path is appended to, e.g. "https://host/api".
   * A root-relative prefix (e.g. "/nba-api") produces root-relative URLs.
   * Used verbatim: callers decide whether to strip a trailing slash.
   */
  baseUrl: string;
  /** Merged into every request's init, e.g. { cache: 'no-store' }. */
  fetchOptions?: RequestInit;
  /** Drop trailing slashes from request paths (a bare "/" is kept). */
  stripTrailingSlash?: boolean;
  /** Message thrown for non-2xx responses. Defaults to defaultErrorFormatter('Request failed'). */
  formatError?: ErrorFormatter;
  /** Message thrown when a 2xx body isn't JSON; null rethrows the SyntaxError. */
  invalidJsonMessage?: string | null;
  /** Treat a failed read of a non-2xx body as an empty body instead of throwing. */
  lenientErrorBody?: boolean;
}

export interface JsonRequestOverrides {
  formatError?: ErrorFormatter;
  invalidJsonMessage?: string | null;
}

export interface ApiClient {
  /** `${baseUrl}${path}` built with URL, plus non-empty query params. */
  url(path: string, params?: QueryParams): string;
  /** `${baseUrl}${pathAndQuery}` concatenated as-is, no normalization or encoding. */
  rawUrl(pathAndQuery: string): string;
  /** fetch() with the configured fetchOptions merged under `init`. */
  fetch(url: string, init?: RequestInit): Promise<Response>;
  getJson<T>(url: string): Promise<T>;
  postJson<T>(url: string, body: unknown, overrides?: JsonRequestOverrides): Promise<T>;
}

// Resolves root-relative URLs; only pathname + search are returned, so the host never leaks.
const RELATIVE_URL_BASE = 'http://relative.invalid';

/**
 * Turn API error response body into a short, readable message.
 * Avoids dumping Django debug HTML or long stack traces into the UI.
 */
export function parseErrorMessage(status: number, body: string): string {
  const statusLabel = status >= 500 ? 'Server error' : 'Request failed';
  // Prefer JSON error payload
  const trimmed = body.trim();
  if (trimmed.startsWith('{')) {
    try {
      const json = JSON.parse(body) as { error?: string; detail?: string; message?: string };
      const msg = json.error ?? json.detail ?? json.message;
      if (typeof msg === 'string' && msg.length > 0 && msg.length < 500) return msg;
    } catch {
      // not JSON, fall through
    }
  }
  // If response looks like HTML (e.g. Django debug page), show generic message
  if (
    trimmed.startsWith('<!') ||
    trimmed.toLowerCase().includes('</html>') ||
    trimmed.toLowerCase().includes('<html')
  ) {
    return status >= 500
      ? `${statusLabel} (${status}). Check the server logs or try again later.`
      : `${statusLabel} (${status}).`;
  }
  // Short plain text is fine to show
  if (body.length <= 200) return body;
  return `${statusLabel} (${status}).`;
}

/** parseErrorMessage, falling back to `${label} (${status})` when it yields nothing. */
export function defaultErrorFormatter(label: string): ErrorFormatter {
  return (status, body) => parseErrorMessage(status, body) || `${label} (${status})`;
}

/** Accept either a bare array or a DRF paginated `{ results: [...] }` payload. */
export function unwrapResults<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results)) {
    return (data as { results: T[] }).results;
  }
  return [];
}

export function createApi(config: ApiClientConfig): ApiClient {
  const {
    baseUrl,
    fetchOptions,
    stripTrailingSlash = false,
    formatError = defaultErrorFormatter('Request failed'),
    invalidJsonMessage = 'Invalid JSON in response',
    lenientErrorBody = false,
  } = config;
  const isRelative = baseUrl.startsWith('/') && !baseUrl.startsWith('//');

  function url(path: string, params?: QueryParams): string {
    const rawPath = path.startsWith('/') ? path : `/${path}`;
    const normalizedPath = stripTrailingSlash && rawPath.length > 1
      ? rawPath.replace(/\/+$/, '')
      : rawPath;
    const built = isRelative
      ? new URL(`${baseUrl}${normalizedPath}`, RELATIVE_URL_BASE)
      : new URL(`${baseUrl}${normalizedPath}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') return;
        built.searchParams.set(key, String(value));
      });
    }
    return isRelative ? `${built.pathname}${built.search}` : built.toString();
  }

  function rawUrl(pathAndQuery: string): string {
    return `${baseUrl}${pathAndQuery}`;
  }

  function request(requestUrl: string, init?: RequestInit): Promise<Response> {
    // Resolve the global fetch per call so runtime patches (e.g. Next.js) apply.
    return fetch(requestUrl, { ...fetchOptions, ...init });
  }

  async function readJson<T>(res: Response, overrides?: JsonRequestOverrides): Promise<T> {
    const toError = overrides?.formatError ?? formatError;
    const badJson = overrides && 'invalidJsonMessage' in overrides
      ? overrides.invalidJsonMessage
      : invalidJsonMessage;
    if (!res.ok) {
      const body = lenientErrorBody ? await res.text().catch(() => '') : await res.text();
      throw new Error(toError(res.status, body));
    }
    const text = await res.text();
    if (badJson === null || badJson === undefined) return JSON.parse(text) as T;
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new Error(badJson);
    }
  }

  return {
    url,
    rawUrl,
    fetch: request,
    async getJson<T>(requestUrl: string): Promise<T> {
      return readJson<T>(await request(requestUrl));
    },
    async postJson<T>(requestUrl: string, body: unknown, overrides?: JsonRequestOverrides): Promise<T> {
      const res = await request(requestUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return readJson<T>(res, overrides);
    },
  };
}
