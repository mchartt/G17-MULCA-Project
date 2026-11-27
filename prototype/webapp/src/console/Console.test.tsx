import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

// No server here: the socket only reports "open" and records what it is asked.
const asked: unknown[] = [];
vi.mock("../lib/socket", () => ({
  SpaceSocket: class {
    constructor(_t: string, _d: unknown, private setStatus: (s: string) => void) {}
    open() {
      this.setStatus("open");
    }
    close() {}
    say() {}
    async ask(frame: unknown) {
      asked.push(frame);
      return { type: "notice", ok: true, text: "On track." };
    }
  },
}));
vi.mock("../lib/account", () => ({ me: async () => null }));

// jsdom has no <dialog> modal: show it as open.
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };

Element.prototype.scrollIntoView = vi.fn();
const { Console } = await import("./Console");

test("the console opens chat first: Your profile, Tour and Quick access in the bar, and the panel beside the chat", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  expect(screen.getByRole("region", { name: "Group chat" })).toBeInTheDocument();
  const bar = screen.getByRole("banner");
  expect(within(bar).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual(["Your profile", "Tour", "Quick access"]);
  const toggle = within(bar).getByRole("button", { name: "Quick access" });
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("complementary", { name: "Quick access" })).toBeInTheDocument();

  await userEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("complementary", { name: "Quick access" })).toBeNull();
  await userEvent.click(toggle);
  await userEvent.click(screen.getByRole("button", { name: "Hide quick access" }));
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(toggle).toHaveFocus();
});

test("Check-in, from Quick access, runs the same command as before", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(within(screen.getByRole("region", { name: "Ask Cadence" })).getByRole("button", { name: /^Check-in/ }));
  expect(asked).toContainEqual({ type: "command", command: "checkin" });
  expect(await screen.findByText("On track.")).toBeInTheDocument();
});

test("the gear next to the space's name opens Project settings, where Delete this space lives", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  expect(screen.queryByRole("button", { name: "Delete this space" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Project settings" }));
  const settings = screen.getByRole("dialog", { name: "Project settings" });
  expect(within(settings).getByLabelText("Name of the space")).toBeInTheDocument();
  expect(within(settings).getByLabelText("Cadence writes in")).toBeInTheDocument();
  await userEvent.click(within(settings).getByRole("button", { name: "Delete this space" }));
  expect(screen.getByRole("dialog", { name: "Delete this space" })).toBeInTheDocument();
});

test("renaming the space from Project settings calls the adapter with the space token", async () => {
  const calls: { url: string; body: unknown; auth: string }[] = [];
  vi.stubGlobal("fetch", async (url: string, init: RequestInit = {}) => {
    calls.push({ url, body: init.body ? JSON.parse(String(init.body)) : null, auth: String((init.headers as Record<string, string>)?.Authorization ?? "") });
    return new Response("{}", { status: 200 });
  });
  render(<Console token="t-rename" onLeave={() => undefined} />);
  await userEvent.click(screen.getByRole("button", { name: "Project settings" }));
  const settings = screen.getByRole("dialog", { name: "Project settings" });
  await userEvent.type(within(settings).getByLabelText("Name of the space"), "AUI group 17");
  await userEvent.click(within(settings).getByRole("button", { name: "Save name" }));
  expect(await within(settings).findByText("Name saved.")).toBeInTheDocument();
  expect(calls.find((c) => c.url.endsWith("/api/groups/rename"))).toMatchObject({ body: { name: "AUI group 17" }, auth: "Bearer t-rename" });
  vi.unstubAllGlobals();
});

test("New task, from the Tasks page, opens a popup; the task goes out as the usual task command and the popup closes when it is accepted", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(within(screen.getByRole("list", { name: "Pages" })).getByRole("button", { name: "Tasks" }));
  await userEvent.click(screen.getByRole("button", { name: "New task" }));
  const popup = screen.getByRole("dialog", { name: "New task" });
  await userEvent.type(within(popup).getByLabelText("Name"), "Test the API");
  await userEvent.type(within(popup).getByLabelText("Description (optional)"), "Contract tests");
  await userEvent.click(within(popup).getByRole("button", { name: "Add task" }));
  expect(asked).toContainEqual({ type: "command", command: "task", args: { add: "Test the API", owner: "", due: "", description: "Contract tests" } });
  expect(await screen.findByText("Task added: “Test the API”.")).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "New task" })).toBeNull();
});

test("New milestone, from the Milestones page, makes a milestone in its own popup", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(within(screen.getByRole("list", { name: "Pages" })).getByRole("button", { name: "Milestones" }));
  await userEvent.click(screen.getByRole("button", { name: "New milestone" }));
  const popup = screen.getByRole("dialog", { name: "New milestone" });
  await userEvent.type(within(popup).getByLabelText("Name"), "Prototype ready");
  await userEvent.type(within(popup).getByLabelText("Date (optional)"), "2026-12-01");
  await userEvent.click(within(popup).getByRole("button", { name: "Add milestone" }));
  expect(asked).toContainEqual({ type: "command", command: "milestone", args: { add: "Prototype ready", due: "2026-12-01" } });
});

test("the left rail opens on the chat; a page replaces the chat and the chat comes back with its own entry", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  const rail = screen.getByRole("list", { name: "Pages" });
  expect(within(rail).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual(["Chat", "Tasks", "Dependencies", "Milestones", "Decisions", "Reflection"]);
  expect(within(rail).getByRole("button", { name: "Chat" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("region", { name: "Group chat" })).toBeInTheDocument();

  await userEvent.click(within(rail).getByRole("button", { name: "Milestones" }));
  expect(within(rail).getByRole("button", { name: "Milestones" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("region", { name: "Milestones" })).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Group chat" })).toBeNull();
  expect(screen.getByRole("heading", { level: 2, name: "Milestones" })).toBeInTheDocument();

  await userEvent.click(within(rail).getByRole("button", { name: "Chat" }));
  expect(screen.getByRole("region", { name: "Group chat" })).toBeInTheDocument();
});

test("a page's New button opens the New task popup", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(within(screen.getByRole("list", { name: "Pages" })).getByRole("button", { name: "Dependencies" }));
  await userEvent.click(screen.getByRole("button", { name: "New task" }));
  expect(screen.getByRole("dialog", { name: "New task" })).toBeInTheDocument();
});

test("Quick access holds six actions that work, none repeating a page (Matteo, 20/11)", () => {
  render(<Console token="t" onLeave={() => undefined} />);
  const panel = screen.getByRole("complementary", { name: "Quick access" });
  const groups = Object.fromEntries(within(panel).getAllByRole("region").map((g) => [g.getAttribute("aria-labelledby"), within(g).getAllByRole("button").map((b) => b.textContent?.trim())]));
  expect(groups).toEqual({
    "quick-cadence": [
      "Catch upWhat changed while you were away: chat, decisions, tasks.",
      "Check-inCompare the plan with the dates and see what slips.",
      "Paste the assignmentCadence proposes the goal, deliverables and milestones.",
      "Find ownersShows every task with no owner; Cadence proposes who could take each.",
    ],
    "quick-plan": [
      "New taskAdd a task; Cadence checks whether it waits on another one.",
      "Add to my calendarA file for Outlook, Google or Apple Calendar: milestones and your tasks.",
    ],
  });
});

test("Find owners and New task open their own popup; Find owners asks for one card", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  for (const [button, title] of [[/^Find owners/, "Find owners"], [/^New task/, "New task"]] as const) {
    await userEvent.click(within(screen.getByRole("complementary", { name: "Quick access" })).getByRole("button", { name: button }));
    const popup = screen.getByRole("dialog", { name: title });
    expect(popup).toBeInTheDocument();
    (popup as HTMLDialogElement).close();
  }
});

test("Catch up only peeks when it opens, and marks it seen when it closes", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(screen.getByRole("button", { name: /^Catch up/ }));
  expect(asked).toContainEqual({ type: "command", command: "catchup", args: { peek: true, recap: true } });
  await userEvent.click(within(screen.getByRole("dialog", { name: "Catch up" })).getByRole("button", { name: "Done" }));
  expect(asked).toContainEqual({ type: "command", command: "catchup", args: { seen: true } });
});

test("Edit the plan, on the Decisions page, opens Project settings where the goal is edited", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(within(screen.getByRole("list", { name: "Pages" })).getByRole("button", { name: "Decisions" }));
  await userEvent.click(screen.getByRole("button", { name: "Edit the plan" }));
  expect(screen.getByRole("dialog", { name: "Project settings" })).toBeInTheDocument();
});

test("the Decisions page is the plan and decision registry, empty until the group confirms something", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(within(screen.getByRole("list", { name: "Pages" })).getByRole("button", { name: "Decisions" }));
  const page = screen.getByRole("region", { name: "Plan and decisions" });
  expect(within(page).getByText(/No goal yet/)).toBeInTheDocument();
  expect(within(page).getByText(/No decision recorded yet/)).toBeInTheDocument();
});

test("the brief written while creating the space goes to Cadence once, as the usual kickoff", async () => {
  sessionStorage.setItem("cadence.brief:t-brief", "Deliver the prototype by 2 December.");
  render(<Console token="t-brief" onLeave={() => undefined} />);
  expect(await screen.findByText(/Cadence read your brief/)).toBeInTheDocument();
  expect(asked).toContainEqual({ type: "command", command: "kickoff", args: { text: "Deliver the prototype by 2 December." } });
  expect(sessionStorage.getItem("cadence.brief:t-brief")).toBeNull();
});

test("Connect Slack or Discord: one button to add Cadence, then the link to paste; voice is Discord only", async () => {
  vi.stubGlobal("fetch", async (url: string) =>
    url.endsWith("/api/connect")
      ? new Response(JSON.stringify({ discord: "https://discord.com/oauth2/authorize?client_id=1", slack: "/api/slack/install" }), { status: 200 })
      : new Response("{}", { status: 200 }),
  );
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(screen.getByRole("button", { name: "Connect Slack or Discord" }));
  const popup = within(screen.getByRole("dialog", { name: "Connect Slack or Discord" }));
  expect(popup.getByRole("radio", { name: "Discord" })).toHaveAttribute("aria-checked", "true");
  expect(await popup.findByRole("link", { name: /Add Cadence to Discord/ })).toHaveAttribute("href", "https://discord.com/oauth2/authorize?client_id=1");
  expect(popup.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  expect(popup.getByText(/one click on the voice channel you use/)).toBeInTheDocument();

  await userEvent.click(popup.getByRole("radio", { name: "Slack" }));
  expect(popup.getByRole("link", { name: /Add Cadence to Slack/ })).toHaveAttribute("href", "/api/slack/install");
  expect(popup.getByText(/\/invite @Cadence/)).toBeInTheDocument();
  expect(popup.getByText(/cannot join Slack huddles/)).toBeInTheDocument();
  vi.unstubAllGlobals();
});

test("Connect says so when this server has no Discord or Slack app, and the link still works", async () => {
  vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ discord: null, slack: null }), { status: 200 }));
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(screen.getByRole("button", { name: "Connect Slack or Discord" }));
  const popup = within(screen.getByRole("dialog", { name: "Connect Slack or Discord" }));
  expect(await popup.findByText(/Discord is not turned on for this Cadence server yet/)).toBeInTheDocument();
  expect(popup.queryByRole("link", { name: /Add Cadence/ })).toBeNull();
  expect(popup.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  vi.unstubAllGlobals();
});

test("Project settings list the documents Cadence reads", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(screen.getByRole("button", { name: "Project settings" }));
  const popup = within(screen.getByRole("dialog", { name: "Project settings" }));
  expect(popup.getByRole("heading", { name: "Documents Cadence reads" })).toBeInTheDocument();
  expect(popup.getByText("No documents yet.")).toBeInTheDocument();
  expect(popup.getByRole("button", { name: /Add a document/ })).toBeInTheDocument();
});

test("below 1100px Quick access is a sheet: it starts closed, focus goes into it, and the page behind is inert until it closes", async () => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: true, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false }));
  render(<Console token="t" onLeave={() => undefined} />);
  const toggle = screen.getByRole("button", { name: "Quick access" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("complementary", { name: "Quick access" })).toBeNull();

  await userEvent.click(toggle);
  expect(screen.getByRole("button", { name: "Hide quick access" })).toHaveFocus();
  expect(document.querySelector(".console__main")).toHaveAttribute("inert");
  expect(document.querySelector(".side")).toHaveAttribute("inert");

  // A shortcut closes the sheet and opens its popup.
  await userEvent.click(screen.getByRole("button", { name: /^Find owners/ }));
  expect(screen.queryByRole("complementary", { name: "Quick access" })).toBeNull();
  expect(screen.getByRole("dialog", { name: "Find owners" })).toBeInTheDocument();
  expect(document.querySelector(".console__main")).not.toHaveAttribute("inert");
  vi.unstubAllGlobals();
});

test("when the window crosses the 1100px breakpoint, Quick access follows: a column that becomes a sheet closes, and back", async () => {
  let matches = false;
  const listeners = new Set<() => void>();
  vi.stubGlobal("matchMedia", (query: string) => ({ get matches() { return matches; }, media: query, addEventListener: (_: string, f: () => void) => listeners.add(f), removeEventListener: (_: string, f: () => void) => listeners.delete(f), onchange: null, dispatchEvent: () => false }));
  render(<Console token="t" onLeave={() => undefined} />);
  expect(screen.getByRole("complementary", { name: "Quick access" })).toBeInTheDocument();

  matches = true;
  await act(async () => listeners.forEach((f) => f()));
  expect(screen.queryByRole("complementary", { name: "Quick access" })).toBeNull();
  expect(screen.getByRole("button", { name: "Quick access" })).toHaveAttribute("aria-expanded", "false");

  matches = false;
  await act(async () => listeners.forEach((f) => f()));
  expect(screen.getByRole("complementary", { name: "Quick access" })).toBeInTheDocument();
  vi.unstubAllGlobals();
});
