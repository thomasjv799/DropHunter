import { createClient } from "@supabase/supabase-js";
let auth;
export async function initializeAuth() {
  const response = await fetch("/api/config");
  const config = await response.json();
  if (!response.ok) throw new Error(config.error);
  auth = createClient(config.url, config.key, {
    auth: { flowType: "pkce", detectSessionInUrl: true },
  });
  return auth;
}
export async function request(path, options = {}) {
  const {
    data: { session },
  } = await auth.auth.getSession();
  if (!session)
    throw Object.assign(new Error("Please sign in again."), { status: 401 });
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + session.access_token,
    },
    signal: AbortSignal.timeout(20000),
  });
  const data = await response.json();
  if (!response.ok)
    throw Object.assign(new Error(data.error || "Request failed."), {
      status: response.status,
    });
  return data;
}
