import { describe, expect, it } from "vitest";
import {
  parseSellingPriceSession,
  serializeSellingPriceSession,
} from "./pro-selling-price-state";

describe("Pro selling-price session", () => {
  it("retains confirmed prices for the same planning squad", () => {
    const raw = serializeSellingPriceSession([3, 1, 2], { 2: 47 });
    expect(parseSellingPriceSession(raw, [1, 2, 3])).toEqual({ 2: 47 });
  });

  it("does not reuse prices for a different squad", () => {
    const raw = serializeSellingPriceSession([1, 2, 3], { 2: 47 });
    expect(parseSellingPriceSession(raw, [1, 2, 4])).toEqual({});
  });

  it("drops corrupt and out-of-range values", () => {
    expect(parseSellingPriceSession("not-json", [1, 2])).toEqual({});
    const raw = JSON.stringify({ squad_key: "1-2", prices: { 1: 301, 2: 45, 9: 40 } });
    expect(parseSellingPriceSession(raw, [1, 2])).toEqual({ 2: 45 });
  });
});
