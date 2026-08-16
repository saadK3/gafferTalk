import { describe, expect, it } from "vitest";
import { isAppHostname, isDemoSquadEnabled } from "./deployment";

describe("deployment host rules", () => {
  it("matches the configured app hostname case-insensitively", () => {
    expect(isAppHostname("APP.GAFFERTALK.COM", "app.gaffertalk.com")).toBe(true);
    expect(isAppHostname("gaffertalk.com", "app.gaffertalk.com")).toBe(false);
  });

  it("exposes the demo squad only in development or on the app hostname", () => {
    expect(isDemoSquadEnabled("localhost", "development", "app.gaffertalk.com")).toBe(true);
    expect(isDemoSquadEnabled("app.gaffertalk.com", "production", "app.gaffertalk.com")).toBe(true);
    expect(isDemoSquadEnabled("gaffertalk.com", "production", "app.gaffertalk.com")).toBe(false);
  });
});
