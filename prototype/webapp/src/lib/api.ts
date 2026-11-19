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

/** Rule 10: delete everything about my space, after typing its name. */
export async function deleteSpace(token: string, confirm: string): Promise<string | null> {
  let res: Response;
  try {
    res = await fetch(`${ADAPTER_URL}/api/groups/delete`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ confirm }),
    });
  } catch {
    return "Cadence can't be reached. Nothing was deleted.";
  }
  if (res.ok) return null;
  if (res.status === 400) return "Type the name of the space exactly as it is written.";
  if (res.status === 502) return "The coordinator server could not delete the data. Nothing was deleted: try again later.";
  return "Something went wrong. Nothing was deleted.";
}

/** Project settings: a new name for my space. Returns the problem to show, or null when renamed. */
export async function renameSpace(token: string, name: string): Promise<string | null> {
  let res: Response;
  try {
    res = await fetch(`${ADAPTER_URL}/api/groups/rename`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  } catch {
    return "Cadence can't be reached. The name was not changed.";
  }
  if (res.ok) return null;
  if (res.status === 422) return "Write a name of 1 to 80 characters.";
  return "Something went wrong. The name was not changed.";
}

/** M5: a new private calendar feed link for my group (the previous one stops working). */
export async function calendarLink(token: string): Promise<string> {
  const res = await fetch(`${ADAPTER_URL}/api/calendar`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new ApiError("The calendar link could not be created. Try again in a moment.");
  const body = await res.json();
  const base = ADAPTER_URL || window.location.origin;
  return `${base}${body.path}`;
}
