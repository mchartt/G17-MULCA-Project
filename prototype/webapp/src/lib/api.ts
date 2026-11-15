// The two HTTP calls of the entry pages, and where the access token lives.
// localStorage is a per-browser convenience only: the server checks the token
// on every request and every socket.

const TOKEN_KEY = "cadence.token";

// Where the web adapter is. Empty: same origin (served by the adapter itself).
// On the static preview (Vercel) set VITE_ADAPTER_URL to a running adapter, or
// leave it empty: the entry then says the live coordinator is not online here.
export const ADAPTER_URL: string = (import.meta.env.VITE_ADAPTER_URL ?? "").replace(/\/$/, "");

export async function adapterOnline(): Promise<boolean> {
  try {
    const res = await fetch(`${ADAPTER_URL}/api/health`, { cache: "no-store" });
    if (!res.ok) return false;
    const body = await res.json();
    return body?.ok === true;
  } catch {
    return false;
  }
}

export function savedToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function saveToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: the session lasts as long as the tab */
  }
}

export class ApiError extends Error {}

async function post(path: string, body: unknown): Promise<{ token: string; inviteCode: string }> {
  let res: Response;
  try {
    res = await fetch(`${ADAPTER_URL}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new ApiError("Cadence can't be reached. Check that the web adapter is running, then try again.");
  }
  if (res.status === 404) throw new ApiError("No space uses this invite code. Check it with the person who shared it.");
  if (res.status === 422) throw new ApiError("Fill in every field (names up to 40 characters).");
  if (!res.ok) throw new ApiError("Something went wrong on the server. Try again in a moment.");
  return res.json();
}

export const createSpace = (groupName: string, displayName: string) => post("/api/groups", { groupName, displayName });
export const joinSpace = (inviteCode: string, displayName: string) => post("/api/join", { inviteCode, displayName });
