import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Browser-safe anon client. RLS allows read-only access to the three echo tables only.
let client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (!client) {
    client = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL as string,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY as string,
      { auth: { persistSession: false } },
    );
  }
  return client;
}
