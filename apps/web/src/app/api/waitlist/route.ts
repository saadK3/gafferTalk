import { NextResponse } from "next/server";

import { addWaitlistSignup } from "@/lib/waitlist";
import { verifyTurnstileToken } from "@/lib/turnstile";

type WaitlistRequest = {
  email?: unknown;
  turnstileToken?: unknown;
  website?: unknown;
};

function isValidEmail(value: string): boolean {
  return value.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export async function POST(request: Request) {
  const payload = (await request.json().catch(() => null)) as WaitlistRequest | null;
  const email = typeof payload?.email === "string" ? payload.email.trim() : "";
  const website = typeof payload?.website === "string" ? payload.website : "";
  const turnstileToken =
    typeof payload?.turnstileToken === "string" ? payload.turnstileToken : undefined;
  if (!isValidEmail(email)) {
    return NextResponse.json(
      { message: "Enter a valid email address." },
      { status: 400 },
    );
  }

  if (website) {
    return NextResponse.json({ message: "You’re on the list." });
  }

  const verified = await verifyTurnstileToken(
    turnstileToken,
    request.headers.get("CF-Connecting-IP"),
  );
  if (!verified) {
    return NextResponse.json(
      { message: "We couldn’t verify this signup. Please try again." },
      { status: 400 },
    );
  }

  const normalizedEmail = email.toLowerCase();
  try {
    const result = await addWaitlistSignup(normalizedEmail);
    return NextResponse.json({
      message:
        result === "created"
          ? "You’re on the list. We’ll see you after Gameweek 1."
          : "You’re already on the list. We’ll be in touch after Gameweek 1.",
    });
  } catch {
    return NextResponse.json(
      { message: "The signup service is unavailable. Please try again shortly." },
      { status: 503 },
    );
  }
}
