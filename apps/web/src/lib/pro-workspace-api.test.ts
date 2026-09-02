import { afterEach, describe, expect, it, vi } from "vitest";
import {
  loadProWorkspace,
  previewWorkspacePlan,
  ProWorkspaceApiError,
  reconcileWorkspacePlan,
  researchWorkspaceNamedTransfer,
  saveWorkspacePlan,
  updateWorkspacePlanLifecycle,
} from "./pro-workspace-api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Pro workspace BFF client", () => {
  it("loads only through the same-origin authenticated BFF", async () => {
    const workspace = {
      entitlement: "pro_beta",
      current_state: null,
      messages: [],
      reports: [],
      plans: [],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(workspace), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadProWorkspace()).resolves.toEqual(workspace);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/pro/workspace",
      expect.objectContaining({ method: "GET", cache: "no-store" }),
    );
  });

  it("forwards only the named-transfer inputs required by the persisted state", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ research: {}, workspace: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const input = {
      outgoing_player_id: 10,
      outgoing_selling_price_tenths: 120,
      target_player_id: 20,
      question: "Should I make this transfer?",
    };

    await researchWorkspaceNamedTransfer(input);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/pro/workspace/research/named-transfer",
      expect.objectContaining({ method: "POST", body: JSON.stringify(input) }),
    );
  });

  it("preserves backend authorization errors for the sign-in redirect", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { code: "invalid_access_token", message: "Sign in again." } }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      ),
    ));

    await expect(loadProWorkspace()).rejects.toEqual(
      new ProWorkspaceApiError("Sign in again.", 401, "invalid_access_token"),
    );
  });

  it("uses explicit same-origin plan lifecycle routes", async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify({ draft: {}, plan: {}, workspace: {} }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const reportId = "11111111-1111-4111-8111-111111111111";
    const planId = "22222222-2222-4222-8222-222222222222";

    await previewWorkspacePlan(reportId);
    await saveWorkspacePlan(reportId);
    await reconcileWorkspacePlan(planId, {
      bank_tenths: 10,
      free_transfers: 1,
      relevant_selling_price_tenths: 120,
    });
    await updateWorkspacePlanLifecycle(planId, "completed");

    expect(fetchMock.mock.calls.map(([path, options]) => [path, options.method])).toEqual([
      ["/api/pro/workspace/plans/preview", "POST"],
      ["/api/pro/workspace/plans", "POST"],
      [`/api/pro/workspace/plans/${planId}/reconcile`, "POST"],
      [`/api/pro/workspace/plans/${planId}`, "PATCH"],
    ]);
  });
});
