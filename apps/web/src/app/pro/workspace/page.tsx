import { redirect } from "next/navigation";
import { supabasePublicConfig } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { ProWorkspaceExperience } from "./pro-workspace-experience";

export default async function ProWorkspacePage() {
  if (!supabasePublicConfig()) redirect("/pro/sign-in");
  const supabase = await createSupabaseServerClient();
  const claims = await supabase.auth.getClaims();
  if (!claims.data?.claims) redirect("/pro/sign-in");
  return <ProWorkspaceExperience />;
}
