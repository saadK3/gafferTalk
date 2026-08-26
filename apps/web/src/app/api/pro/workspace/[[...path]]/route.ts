import { createSupabaseServerClient } from "@/lib/supabase/server";

type Context = { params: Promise<{ path?: string[] }> };

const allowedPaths = new Map([
  ["GET:", "/v1/pro/workspace"],
  ["PUT:state", "/v1/pro/workspace/state"],
  ["POST:research/named-transfer", "/v1/pro/workspace/research/named-transfer"],
]);

function apiBaseUrl(): string {
  return (
    process.env.GAFFERTALK_API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000"
  ).replace(/\/$/, "");
}

async function forward(request: Request, context: Context): Promise<Response> {
  const { path = [] } = await context.params;
  const targetPath = allowedPaths.get(`${request.method}:${path.join("/")}`);
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
