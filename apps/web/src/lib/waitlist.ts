import { getCloudflareContext } from "@opennextjs/cloudflare";
import { createWaitlistTableSql } from "../../db/schema";

type WaitlistInsertResult = "created" | "existing";

export async function addWaitlistSignup(email: string): Promise<WaitlistInsertResult> {
  const { env } = getCloudflareContext();
  const now = new Date().toISOString();

  await env.DB.prepare(createWaitlistTableSql).run();

  const result = await env.DB.prepare(
    `INSERT OR IGNORE INTO waitlist_signups
      (id, email, source, consented_at, created_at)
     VALUES (?, ?, ?, ?, ?)`,
  )
    .bind(crypto.randomUUID(), email, "prelaunch-landing", now, now)
    .run();

  return result.meta.changes === 0 ? "existing" : "created";
}
