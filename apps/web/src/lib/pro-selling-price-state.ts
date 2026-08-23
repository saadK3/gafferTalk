export const PRO_SELLING_PRICE_SESSION_KEY = "gaffertalk.proSellingPrices.v1";

type SellingPriceSession = {
  squad_key: string;
  prices: Record<number, number>;
};

function squadKey(playerIds: number[]) {
  return [...playerIds].sort((left, right) => left - right).join("-");
}

export function parseSellingPriceSession(
  raw: string | null,
  playerIds: number[],
): Record<number, number> {
  if (!raw) return {};
  try {
    const value = JSON.parse(raw) as Partial<SellingPriceSession>;
    if (value.squad_key !== squadKey(playerIds) || !value.prices) return {};
    const allowed = new Set(playerIds);
    return Object.fromEntries(
      Object.entries(value.prices)
        .map(([playerId, price]) => [Number(playerId), Number(price)] as const)
        .filter(([playerId, price]) => (
          allowed.has(playerId)
          && Number.isInteger(price)
          && price >= 0
          && price <= 300
        )),
    );
  } catch {
    return {};
  }
}

export function serializeSellingPriceSession(
  playerIds: number[],
  prices: Record<number, number>,
) {
  return JSON.stringify({ squad_key: squadKey(playerIds), prices } satisfies SellingPriceSession);
}
