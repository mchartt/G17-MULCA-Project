// Accounts: register, log in, my profile, my spaces (web adapter: account_routes.py).
//
// Two tokens live in this browser, on purpose:
//   - the account token says who you are (this file);
//   - the space token opens one space as you (api.ts, used by the console).
import { ADAPTER_URL, ApiError } from "./api";

const ACCOUNT_KEY = "cadence.account";

export type User = {
  id: number;
  email: string;
  displayName: string;
  discipline: string;
  skills: string[];
  weeklyHours: number | null;
};
export type SpaceRef = { id: number; name: string; inviteCode: string };
export type ProfileInput = Pick<User, "displayName" | "discipline" | "skills" | "weeklyHours">;
type Session = { accountToken: string; user: User };
type SpaceAccess = { token: string; inviteCode: string; memberId: number };

export function savedAccount(): string | null {
  try {
    return localStorage.getItem(ACCOUNT_KEY);
  } catch {
    return null;
  }
}

export function saveAccount(token: string | null): void {
  try {
    if (token) localStorage.setItem(ACCOUNT_KEY, token);
    else localStorage.removeItem(ACCOUNT_KEY);
  } catch {
    /* private mode: the login lasts as long as the tab */
  }
}

/** One call to the adapter. The server's own words are shown when it explains the problem. */
async function call<T>(method: "GET" | "POST" | "PUT", path: string, body?: unknown, token?: string | null): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${ADAPTER_URL}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Cadence can't be reached. Check your connection, then try again.");
  }
  if (res.ok) return res.json();
  if (res.status === 422) throw new ApiError("Check the fields: something is missing or too long.");
  let detail = "";
  try {
    detail = (await res.json()).detail;
  } catch {
    /* no explanation from the server */
  }
  throw new ApiError(typeof detail === "string" && detail ? detail : "Something went wrong on the server. Try again in a moment.");
}

export async function register(email: string, password: string, displayName: string): Promise<User> {
  const session = await call<Session>("POST", "/api/register", { email, password, displayName });
  saveAccount(session.accountToken);
  return session.user;
}

export async function login(email: string, password: string): Promise<User> {
  const session = await call<Session>("POST", "/api/login", { email, password });
  saveAccount(session.accountToken);
  return session.user;
}

export async function logout(): Promise<void> {
  const token = savedAccount();
  saveAccount(null);
  if (token) await call("POST", "/api/logout", undefined, token).catch(() => undefined);
}

/** Who is logged in on this browser and their spaces, or null (never throws). */
export async function me(): Promise<{ user: User; spaces: SpaceRef[] } | null> {
  const token = savedAccount();
  if (!token) return null;
  try {
    return await call("GET", "/api/me", undefined, token);
  } catch {
    return null;
  }
}

export async function saveProfile(profile: ProfileInput): Promise<User> {
  return (await call<{ user: User }>("PUT", "/api/me", profile, savedAccount())).user;
}

export const createMySpace = (groupName: string) => call<SpaceAccess>("POST", "/api/groups", { groupName }, savedAccount());
export const joinMySpace = (inviteCode: string) => call<SpaceAccess>("POST", "/api/join", { inviteCode }, savedAccount());
export const openMySpace = (groupId: number) => call<SpaceAccess>("POST", "/api/spaces/open", { groupId }, savedAccount());
