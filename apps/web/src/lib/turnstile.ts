import { getCloudflareContext } from "@opennextjs/cloudflare";

type TurnstileResponse = {
  success: boolean;
};

export async function verifyTurnstileToken(
  token: string | undefined,
  remoteIp: string | null,
): Promise<boolean> {
  const { env } = getCloudflareContext();
  const secret = env.TURNSTILE_SECRET_KEY;

  if (!secret) {
    return process.env.NODE_ENV !== "production";
  }
  if (!token) {
    return false;
  }

  const formData = new FormData();
  formData.set("secret", secret);
  formData.set("response", token);
  if (remoteIp) {
    formData.set("remoteip", remoteIp);
  }

  const response = await fetch(
    "https://challenges.cloudflare.com/turnstile/v0/siteverify",
    { method: "POST", body: formData },
  );
  if (!response.ok) {
    return false;
  }

  const result = (await response.json()) as TurnstileResponse;
  return result.success;
}
