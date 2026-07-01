import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';

const BACKEND_ORIGIN = (
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'http://127.0.0.1:8000'
).replace(/\/$/, '');

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

function buildBackendUrl(path: string[], request: NextRequest): string {
  const joinedPath = path.map(encodeURIComponent).join('/');
  const url = new URL(`/api/nba/${joinedPath}/`, BACKEND_ORIGIN);
  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.append(key, value);
  });
  return url.toString();
}

function responseHeaders(response: Response): Headers {
  const headers = new Headers(response.headers);
  headers.delete('content-encoding');
  headers.delete('content-length');
  headers.delete('transfer-encoding');
  return headers;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const response = await fetch(buildBackendUrl(path, request), {
    method: request.method,
    headers: {
      accept: request.headers.get('accept') || 'application/json',
    },
    cache: 'no-store',
  });

  if (request.method === 'HEAD') {
    return new Response(null, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders(response),
    });
  }

  return new Response(await response.arrayBuffer(), {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders(response),
  });
}

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context);
}

export async function HEAD(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context);
}
