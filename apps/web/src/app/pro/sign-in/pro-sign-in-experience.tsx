"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { createSupabaseBrowserClient } from "@/lib/supabase/client";
import styles from "../workspace/workspace.module.css";

export function ProSignInExperience() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [stage, setStage] = useState<"email" | "otp">("email");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const sendCode = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const supabase = createSupabaseBrowserClient();
    const result = await supabase.auth.signInWithOtp({
      email: email.trim().toLowerCase(),
      options: { shouldCreateUser: true },
    });
    setBusy(false);
    if (result.error) {
      setError(result.error.message);
      return;
    }
    setStage("otp");
  };

  const verifyCode = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    const supabase = createSupabaseBrowserClient();
    const result = await supabase.auth.verifyOtp({
      email: email.trim().toLowerCase(),
      token: otp.trim(),
      type: "email",
    });
    setBusy(false);
    if (result.error) {
      setError(result.error.message);
      return;
    }
    router.replace("/pro/workspace");
    router.refresh();
  };

  return (
    <main className={styles.authPage}>
      <section className={styles.authCard}>
        <Link className={styles.wordmark} href="/">GafferTalk<span>.</span></Link>
        <p className={styles.eyebrow}>Private Pro beta</p>
        <h1>{stage === "email" ? "Sign in to your workspace." : "Check your email."}</h1>
        <p>
          {stage === "email"
            ? "We’ll send a one-time code. No password—and no FPL credentials—required."
            : `Enter the six-digit code sent to ${email}.`}
        </p>
        {stage === "email" ? (
          <form onSubmit={sendCode}>
            <label htmlFor="pro-email">Email address</label>
            <input id="pro-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
            <button type="submit" disabled={busy}>{busy ? "Sending…" : "Send sign-in code"}</button>
          </form>
        ) : (
          <form onSubmit={verifyCode}>
            <label htmlFor="pro-otp">One-time code</label>
            <input id="pro-otp" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={otp} onChange={(event) => setOtp(event.target.value.replace(/\D/g, ""))} />
            <button type="submit" disabled={busy || otp.length !== 6}>{busy ? "Signing in…" : "Open my workspace"}</button>
            <button className={styles.textButton} type="button" onClick={() => { setStage("email"); setOtp(""); setError(""); }}>Use a different email</button>
          </form>
        )}
        {error ? <p className={styles.error} role="alert">{error}</p> : null}
        <small>Signing in creates an account-scoped research workspace. Your public FPL Team ID is connected separately.</small>
      </section>
    </main>
  );
}
