export const FREE_CLIENT_ID_STORAGE_KEY = "gaffertalk.freeClientId.v1";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type StorageLike = Pick<Storage, "getItem" | "setItem">;

export function getOrCreateFreeClientId(
  storage: StorageLike,
  createId: () => string = () => crypto.randomUUID(),
): string {
  const existing = storage.getItem(FREE_CLIENT_ID_STORAGE_KEY);
  if (existing && UUID_PATTERN.test(existing)) return existing;

  const created = createId();
  if (!UUID_PATTERN.test(created)) throw new Error("Could not create a valid browser ID.");
  storage.setItem(FREE_CLIENT_ID_STORAGE_KEY, created);
  return created;
}
