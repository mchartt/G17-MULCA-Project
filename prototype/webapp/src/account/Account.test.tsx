// The account screens against a fake adapter: every fetch is answered by `server`.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { CatchUpDialog } from "../console/CatchUpDialog";
import { emptySpace, nameOf, reduce } from "../console/space";
import { LoginPage } from "./LoginPage";
import { savedAccount } from "../lib/account";
import { savedToken } from "../lib/api";

const ADA = { id: 1, email: "ada@example.org", displayName: "Ada", discipline: "", skills: [], weeklyHours: null };

// jsdom has no <dialog> modal: show it as open.
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };

/** The login page as App mounts it: /login is the home, /login/new the setup desk. */
function Page({ onEnter = vi.fn(), start = "/login" }: { onEnter?: (token: string) => void; start?: string }) {
  const [path, setPath] = useState(start);
  return <LoginPage path={path} onNavigate={setPath} onEnter={onEnter} />;
}

type Call = { method: string; path: string; body?: Record<string, unknown>; token?: string };
let calls: Call[];
let server: (call: Call) => { status?: number; json: unknown };

beforeEach(() => {
  calls = [];
  localStorage.clear();
  sessionStorage.clear();
  vi.stubGlobal("fetch", async (url: string, init: RequestInit = {}) => {
    const call: Call = {
      method: init.method ?? "GET",
      path: new URL(url, "http://t").pathname,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
      token: (init.headers as Record<string, string> | undefined)?.Authorization?.replace("Bearer ", ""),
    };
    calls.push(call);
    const { status = 200, json } = server(call);
    return new Response(JSON.stringify(json), { status });
  });
  // jsdom has no IntersectionObserver (the reveal animation uses it).
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} });
});

test("create an account, then the guided setup: profile, ready, a project on the setup desk", async () => {
  const onEnter = vi.fn();
  let spaces: unknown[] = [];
  server = ({ method, path, token, body }) => {
    if (path === "/api/health") return { json: { ok: true } };
    if (path === "/api/register") return { json: { accountToken: "acc-1", user: ADA } };
    if (path === "/api/me" && method === "PUT") return { json: { user: { ...ADA, ...body } } };
    if (path === "/api/me" && method === "GET") return token === "acc-1" ? { json: { user: ADA, spaces } } : { status: 401, json: { detail: "Log in again." } };
    if (path === "/api/groups") {
      spaces = [{ id: 7, name: "Team 17", inviteCode: "AB12CD" }];
      return { json: { token: "space-1", inviteCode: "AB12CD", memberId: 100000001 } };
    }
    return { status: 500, json: {} };
  };
  render(<Page onEnter={onEnter} />);

  // The box must be ticked before an account is made.
  await userEvent.type(await screen.findByLabelText(/Your name/), "Ada");
  await userEvent.type(screen.getByLabelText("Email"), "ada@example.org");
  await userEvent.type(screen.getByLabelText(/Password/), "correct horse");
  await userEvent.click(screen.getByRole("button", { name: /Create my account/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent("tick the box");
  expect(calls.some((c) => c.path === "/api/register")).toBe(false);

  await userEvent.click(screen.getByLabelText("I have read this and I agree"));
  await userEvent.click(screen.getByRole("button", { name: /Create my account/ }));
  expect(await screen.findByRole("heading", { name: "What should your group call you?" })).toBeInTheDocument();
  expect(savedAccount()).toBe("acc-1");

  // One question per screen; the name is already there from the sign-up.
  expect(screen.getByLabelText("Your name")).toHaveValue("Ada");
  await userEvent.click(screen.getByRole("button", { name: /Continue/ }));
  await userEvent.type(screen.getByLabelText("What you study"), "HCI");
  await userEvent.click(screen.getByRole("button", { name: /Continue/ }));
  await userEvent.type(screen.getByLabelText("Skills"), "figma,");
  await userEvent.click(screen.getByRole("button", { name: /Save my profile/ }));
  expect(await screen.findByRole("heading", { name: "Don't worry, your profile is set up." })).toBeInTheDocument();
  expect(calls.find((c) => c.method === "PUT")?.body).toMatchObject({ displayName: "Ada", discipline: "HCI", skills: ["figma"] });

  await userEvent.click(screen.getByRole("button", { name: /Create a project/ }));
  expect(screen.getByRole("heading", { name: "Set up a new project" })).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Project name"), "Team 17");
  await userEvent.type(screen.getByLabelText("What is the project about?"), "AUI prototype, demo on 2 December.");
  await userEvent.click(screen.getByRole("button", { name: /Create the space/ }));
  await waitFor(() => expect(onEnter).toHaveBeenCalledWith("space-1"));
  expect(calls.find((c) => c.path === "/api/groups")).toMatchObject({ body: { groupName: "Team 17" }, token: "acc-1" });
  expect(savedToken()).toBe("space-1");
  // The description waits for the console, which sends it to Cadence as the brief.
  expect(sessionStorage.getItem("cadence.brief:space-1")).toBe("AUI prototype, demo on 2 December.");
});

test("invited, a new account finishes the profile and finds Join first, with the code filled in", async () => {
  history.replaceState(null, "", "/login?code=AB12CD");
  localStorage.setItem("cadence.account", "acc-1");
  server = ({ path, method, body }) => {
    if (path === "/api/health") return { json: { ok: true } };
    if (path === "/api/me" && method === "GET") return { json: { user: ADA, spaces: [] } };
    if (path === "/api/me" && method === "PUT") return { json: { user: { ...ADA, ...body } } };
    return { status: 500, json: {} };
  };
  render(<Page />);
  await userEvent.click(await screen.findByRole("button", { name: /Continue/ }));
  await userEvent.click(screen.getByRole("button", { name: /Continue/ }));
  await userEvent.click(screen.getByRole("button", { name: /Save my profile/ }));
  await screen.findByRole("heading", { name: "Don't worry, your profile is set up." });
  const choices = screen.getAllByRole("button").filter((b) => b.classList.contains("choice"));
  expect(choices[0]).toHaveTextContent("Join a project");
  expect(choices[0]).toHaveTextContent("the code is already filled in");
  await userEvent.click(choices[0]!);
  expect(screen.getByLabelText("Invite code")).toHaveValue("AB12CD");
  history.replaceState(null, "", "/");
});

test("the guided setup can be skipped: the home has New project and the join line; the desk comes and goes", async () => {
  localStorage.setItem("cadence.account", "acc-1");
  server = ({ path, method }) => {
    if (path === "/api/health") return { json: { ok: true } };
    if (path === "/api/me" && method === "GET") return { json: { user: ADA, spaces: [] } };
    return { status: 500, json: {} };
  };
  render(<Page />);
  await userEvent.click(await screen.findByRole("button", { name: "Skip for now" }));
  expect(screen.getByRole("heading", { name: /Your projects/ })).toBeInTheDocument();
  expect(screen.getByText("No projects yet.")).toBeInTheDocument();
  expect(screen.getByLabelText("Invite code")).toBeInTheDocument();
  expect(screen.queryByLabelText("Project name")).toBeNull();

  await userEvent.click(screen.getByRole("button", { name: /New project/ }));
  expect(screen.getByLabelText("Project name")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Your projects/ }));
  expect(screen.getByRole("button", { name: /New project/ })).toBeInTheDocument();
});

test("documents added to a new project show as sheets, each with its own remove button", async () => {
  localStorage.setItem("cadence.account", "acc-1");
  server = ({ path, method }) => {
    if (path === "/api/health") return { json: { ok: true } };
    if (path === "/api/me" && method === "GET") return { json: { user: { ...ADA, skills: ["figma"] }, spaces: [] } };
    return { status: 500, json: {} };
  };
  const { container } = render(<Page start="/login/new" />);
  await screen.findByLabelText("Project name");
  const picker = container.querySelector<HTMLInputElement>('input[type="file"]')!;
  await userEvent.upload(picker, [new File(["brief"], "brief.pdf", { type: "application/pdf" }), new File(["notes"], "notes.md", { type: "text/markdown" })]);
  const shelf = screen.getByRole("list", { name: "Documents added" });
  expect(shelf).toHaveTextContent("brief.pdf");
  expect(shelf).toHaveTextContent("notes.md");
  await userEvent.click(screen.getByRole("button", { name: "Remove brief.pdf" }));
  expect(screen.getByRole("list", { name: "Documents added" })).not.toHaveTextContent("brief.pdf");
});

test("log in shows the server's words on a wrong password, then your spaces to open", async () => {
  const onEnter = vi.fn();
  let attempts = 0;
  server = ({ path, method }) => {
    if (path === "/api/health") return { json: { ok: true } };
    if (path === "/api/login") return ++attempts === 1 ? { status: 401, json: { detail: "Email or password not correct." } } : { json: { accountToken: "acc-2", user: ADA } };
    if (path === "/api/me" && method === "GET") return localStorage.getItem("cadence.account") ? { json: { user: ADA, spaces: [{ id: 7, name: "Team 17", inviteCode: "AB12CD" }] } } : { status: 401, json: {} };
    if (path === "/api/spaces/open") return { json: { token: "space-9", inviteCode: "AB12CD", memberId: 1 } };
    if (path === "/api/logout") return { json: { ok: true } };
    return { status: 500, json: {} };
  };
  render(<Page onEnter={onEnter} />);

  await userEvent.click(await screen.findByRole("tab", { name: "Log in" }));
  await userEvent.type(screen.getByLabelText("Email"), "ada@example.org");
  await userEvent.type(screen.getByLabelText("Password"), "wrong");
  await userEvent.click(screen.getByRole("button", { name: /^Log in/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Email or password not correct.");
  await userEvent.click(screen.getByRole("button", { name: /^Log in/ }));

  await userEvent.click(await screen.findByRole("button", { name: /Open/ }));
  await waitFor(() => expect(onEnter).toHaveBeenCalledWith("space-9"));
  expect(calls.find((c) => c.path === "/api/spaces/open")).toMatchObject({ body: { groupId: 7 }, token: "acc-2" });

  await userEvent.click(screen.getByRole("button", { name: /Log out/ }));
  expect(await screen.findByRole("tab", { name: "Create an account" })).toBeInTheDocument();
  expect(savedAccount()).toBeNull();
});

test("the profile is saved once in the account", async () => {
  localStorage.setItem("cadence.account", "acc-1");
  server = ({ path, method, body }) => {
    if (path === "/api/health") return { json: { ok: true } };
    if (path === "/api/me" && method === "GET") return { json: { user: ADA, spaces: [] } };
    if (path === "/api/me" && method === "PUT") return { json: { user: { ...ADA, ...body } } };
    return { status: 500, json: {} };
  };
  render(<Page />);
  await userEvent.click(await screen.findByRole("button", { name: "Skip for now" }));
  await userEvent.click(await screen.findByRole("button", { name: /My profile/ }));
  expect(screen.getByRole("dialog", { name: "My profile" })).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Discipline"), "HCI");
  await userEvent.type(screen.getByLabelText(/Skills/), "figma, ux research ,");
  await userEvent.type(screen.getByLabelText(/Hours per week/), "6");
  await userEvent.click(screen.getByRole("button", { name: "Save profile" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Profile saved");
  expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ displayName: "Ada", discipline: "HCI", skills: ["figma", "ux research"], weeklyHours: 6, background: "" });
});

test("many projects come a page at a time, with a filter, never as one long list", async () => {
  localStorage.setItem("cadence.account", "acc-1");
  const spaces = Array.from({ length: 14 }, (_, i) => ({ id: i + 1, name: `Project ${String.fromCharCode(65 + i)}`, inviteCode: `CODE${i}` }));
  server = ({ path, method }) => {
    if (path === "/api/health") return { json: { ok: true } };
    if (path === "/api/me" && method === "GET") return { json: { user: { ...ADA, skills: ["figma"] }, spaces } };
    return { status: 500, json: {} };
  };
  render(<Page />);
  // Without a measured box (jsdom) six tiles fit: three columns by two rows.
  const list = await screen.findByRole("list", { name: "Projects" });
  expect(within(list).getAllByRole("button")).toHaveLength(6);
  expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Open Project G" })).toBeInTheDocument();

  await userEvent.type(screen.getByLabelText("Find a project"), "project n");
  expect(within(screen.getByRole("list", { name: "Projects" })).getAllByRole("button")).toHaveLength(1);
  expect(screen.queryByRole("navigation", { name: "Pages of projects" })).toBeNull();
  await userEvent.clear(screen.getByLabelText("Find a project"));
  await userEvent.type(screen.getByLabelText("Find a project"), "nothing like it");
  expect(screen.getByText(/No project matches/)).toBeInTheDocument();
});

test("the privacy notice opens from the home, and from the nav's Privacy link", async () => {
  history.replaceState(null, "", "/login#privacy");
  localStorage.setItem("cadence.account", "acc-1");
  server = ({ path, method }) => {
    if (path === "/api/health") return { json: { ok: true } };
    if (path === "/api/me" && method === "GET") return { json: { user: { ...ADA, skills: ["figma"] }, spaces: [] } };
    return { status: 500, json: {} };
  };
  render(<Page />);
  const notice = await screen.findByRole("dialog", { name: "What Cadence reads and keeps" });
  expect(notice).toHaveTextContent("Azure OpenAI");
  history.replaceState(null, "", "/");
});

test("catch up lists what was decided and said in the other channel", () => {
  render(
    <CatchUpDialog
      open
      inviteCode="AB12CD"
      onClose={vi.fn()}
      summary="Since your last catch-up: 1 decision, 2 messages on Discord."
      catchup={{
        since: 0, until: 100, linked: true,
        decisions: [{ question: "Which lab slot?", choice: "Tuesday 17:00", reason: "Everyone is free", decided_at: 50 }],
        elsewhere: [{ channel: "discord", total: 5, messages: [{ speaker: "Chiara", text: "Lab on Tuesday?", at: 40 }, { speaker: "Dario", text: "Yes", at: 45 }] }],
      }}
    />,
  );
  expect(screen.getByText("Tuesday 17:00")).toBeInTheDocument();
  expect(screen.getByText("On Discord")).toBeInTheDocument();
  expect(screen.getByText("3 earlier messages not shown.")).toBeInTheDocument();
  expect(screen.getByText(/Lab on Tuesday\?/)).toBeInTheDocument();
});

test("a group that is not linked is told how to link a channel", () => {
  render(<CatchUpDialog open inviteCode="AB12CD" onClose={vi.fn()} summary="Not linked yet." catchup={{ since: 0, until: 1, linked: false, decisions: [], elsewhere: [] }} />);
  expect(screen.getByText("/coordinator link AB12CD")).toBeInTheDocument();
});

test("names of members from a linked channel come with cards and states", () => {
  const big = "4611686018427387999"; // a Slack member: sent as text, too large for a number
  let space = reduce(emptySpace, { type: "members", members: [{ id: 100000001, name: "Ada" }] });
  space = reduce(space, { type: "state", state: { names: { [big]: "Chiara" } } });
  space = reduce(space, { type: "proposal", proposal: { proposal_id: "p1", kind: "plan", status: "pending", payload: {}, names: { "9002": "Dario" } } });
  expect(nameOf(100000001, space)).toBe("Ada");
  expect(nameOf(big, space)).toBe("Chiara");
  expect(nameOf(9002, space)).toBe("Dario");
  expect(nameOf(42, space)).toBeUndefined();
});
