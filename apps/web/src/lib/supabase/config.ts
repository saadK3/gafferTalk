export type SupabasePublicConfig = {
  url: string;
  publishableKey: string;
};

export function supabasePublicConfig(): SupabasePublicConfig | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const publishableKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();
  if (!url || !publishableKey) return null;
  return { url: url.replace(/\/$/, ""), publishableKey };
}

export function requireSupabasePublicConfig(): SupabasePublicConfig {
  const config = supabasePublicConfig();
  if (!config) throw new Error("Supabase authentication is not configured.");
  return config;
}
