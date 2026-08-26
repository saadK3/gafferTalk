import Link from "next/link";
import { redirect } from "next/navigation";
import { supabasePublicConfig } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { ProSignInExperience } from "./pro-sign-in-experience";
import styles from "../workspace/workspace.module.css";

export default async function ProSignInPage() {
  if (!supabasePublicConfig()) {
    return (
      <main className={styles.authPage}>
        <section className={styles.authCard}>
          <Link className={styles.wordmark} href="/">GafferTalk<span>.</span></Link>
          <p className={styles.eyebrow}>Pro workspace setup</p>
          <h1>Authentication needs local configuration.</h1>
          <p>Add the public Supabase URL and publishable key described in the Pro workspace runbook.</p>
        </section>
      </main>
    );
  }
  const supabase = await createSupabaseServerClient();
  const claims = await supabase.auth.getClaims();
  if (claims.data?.claims) redirect("/pro/workspace");
  return <ProSignInExperience />;
}
