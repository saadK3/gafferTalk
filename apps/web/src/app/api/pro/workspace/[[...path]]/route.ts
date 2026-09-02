import { createSupabaseServerClient } from "@/lib/supabase/server";

type Context = { params: Promise<{ path?: string[] }> };

const allowedPaths = new Map([
  ["GET:", "/v1/pro/workspace"],
  ["PUT:state", "/v1/pro/workspace/state"],
  ["POST:research/named-transfer", "/v1/pro/workspace/research/named-transfer"],
  ["POST:plans/preview", "/v1/pro/workspace/plans/preview"],
  ["POST:plans", "/v1/pro/workspace/plans"],
]);

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function resolveTargetPath(method: string, path: string[]): string | undefined {
  const fixed = allowedPaths.get(`${method}:${path.join("/")}`);
  if (fixed) return fixed;
  if (path[0] !== "plans" || !path[1] || !UUID_PATTERN.test(path[1])) return undefined;
  if (method === "POST" && path.length === 3 && path[2] === "reconcile") {
    return `/v1/pro/workspace/plans/${path[1]}/reconcile`;
  }
  if (method === "PATCH" && path.length === 2) {
    return `/v1/pro/workspace/plans/${path[1]}`;
  }
  return undefined;
}

function apiBaseUrl(): string {
  return (
    process.env.GAFFERTALK_API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

async function forward(request: Request, context: Context): Promise<Response> {
  const { path = [] } = await context.params;
  const targetPath = resolveTargetPath(request.method, path);
  if (!targetPath) return Response.json({ detail: "Not found" }, { status: 404 });

  const supabase = await createSupabaseServerClient();
  const claims = await supabase.auth.getClaims();
  const session = await supabase.auth.getSession();
  const accessToken = session.data.session?.access_token;
  if (claims.error || !claims.data?.claims || !accessToken) {
    return Response.json(
      { detail: { code: "authentication_required", message: "Sign in to continue." } },
      { status: 401 },
    );
  }

  const body = request.method === "GET" ? undefined : await request.text();
  try {
    const response = await fetch(`${apiBaseUrl()}${targetPath}`, {
      method: request.method,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body,
    });
    return new Response(await response.text(), {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
    });
  } catch {
    return Response.json(
      {
        detail: {
          code: "workspace_unavailable",
          message: "The Pro workspace service is unavailable. Try again shortly.",
        },
      },
      { status: 503 },
    );
  }
}

export function GET(request: Request, context: Context) {
  return forward(request, context);
}

export function PUT(request: Request, context: Context) {
  return forward(request, context);
}

export function POST(request: Request, context: Context) {
  return forward(request, context);
}

export function PATCH(request: Request, context: Context) {
  return forward(request, context);
}
