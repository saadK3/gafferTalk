"use client";

import Script from "next/script";
import { FormEvent, useState } from "react";

type SubmissionState = "idle" | "submitting" | "success" | "error";

declare global {
  interface Window {
    turnstile?: { reset: () => void };
  }
}

export function WaitlistForm() {
  const [state, setState] = useState<SubmissionState>("idle");
  const [message, setMessage] = useState("");
  const siteKey =
    process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ??
    (process.env.NODE_ENV === "production" ? "0x4AAAAAAEORSMZ-bDSldmos" : undefined);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState("submitting");
    setMessage("");

    const form = event.currentTarget;
    const data = new FormData(form);
    const response = await fetch("/api/waitlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: data.get("email"),
        website: data.get("website"),
        turnstileToken: data.get("cf-turnstile-response") || undefined,
      }),
    }).catch(() => null);

    if (!response) {
      setState("error");
      setMessage("The signup service is unavailable. Please try again shortly.");
      return;
    }

    const payload = (await response.json().catch(() => ({}))) as { message?: string };
    window.turnstile?.reset();
    if (!response.ok) {
      setState("error");
      setMessage(payload.message ?? "We couldn’t save your signup. Please try again.");
      return;
    }

    setState("success");
    setMessage(payload.message ?? "You’re on the list.");
    form.reset();
  }

  return (
    <>
      {siteKey ? (
        <Script
          src="https://challenges.cloudflare.com/turnstile/v0/api.js"
          strategy="afterInteractive"
        />
      ) : null}
      <form className="signup-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="email">Email address</label>
        <input
          autoComplete="email"
          id="email"
          name="email"
          type="email"
          placeholder="you@example.com"
          required
        />
        <label className="honeypot" aria-hidden="true">
          Website
          <input name="website" tabIndex={-1} autoComplete="off" />
        </label>
        {siteKey ? (
          <div
            className="cf-turnstile"
            data-sitekey={siteKey}
            data-theme="light"
            data-size="flexible"
          />
        ) : null}
        <button type="submit" disabled={state === "submitting"}>
          {state === "submitting" ? "Joining…" : "Join the list"}
          <span aria-hidden="true">→</span>
        </button>
      </form>
      <p
        className={`signup-message ${state}`}
        role="status"
        aria-live="polite"
      >
        {message}
      </p>
    </>
  );
}
