import { describe, expect, it } from "vitest";
import { FREE_CLIENT_ID_STORAGE_KEY, getOrCreateFreeClientId } from "./free-plan";

const VALID_ID = "00000000-0000-4000-8000-000000000001";

function storage(initial?: string) {
  const values = new Map<string, string>();
  if (initial) values.set(FREE_CLIENT_ID_STORAGE_KEY, initial);
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    values,
  };
}

describe("anonymous Free identity", () => {
  it("keeps a valid browser ID", () => {
    const local = storage(VALID_ID);
    expect(getOrCreateFreeClientId(local, () => { throw new Error("not needed"); })).toBe(VALID_ID);
  });

  it("replaces missing or corrupt browser state", () => {
    const local = storage("not-a-uuid");
    expect(getOrCreateFreeClientId(local, () => VALID_ID)).toBe(VALID_ID);
    expect(local.values.get(FREE_CLIENT_ID_STORAGE_KEY)).toBe(VALID_ID);
  });
});
