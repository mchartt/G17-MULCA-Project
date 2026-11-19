import { render, screen, within } from "@testing-library/react";
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

test("the console opens chat first: one Quick access button in the bar, and the panel it shows beside the chat", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  expect(screen.getByRole("region", { name: "Group chat" })).toBeInTheDocument();
  const bar = screen.getByRole("banner");
  expect(within(bar).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual(["Quick access"]);
  const toggle = within(bar).getByRole("button", { name: "Quick access" });
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("complementary", { name: "Quick access" })).toBeInTheDocument();

  await userEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("complementary", { name: "Quick access" })).toBeNull();
  await userEvent.click(toggle);
  await userEvent.click(screen.getByRole("button", { name: "Close quick access" }));
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

test("Quick access holds what is not on a page: Ask Cadence, the dates, project memory and the member, with no copy of Tasks or Milestones", () => {
  render(<Console token="t" onLeave={() => undefined} />);
  const panel = screen.getByRole("complementary", { name: "Quick access" });
  const groups = Object.fromEntries(within(panel).getAllByRole("region").map((g) => [g.getAttribute("aria-labelledby"), within(g).getAllByRole("button").map((b) => b.textContent?.trim())]));
  expect(groups).toEqual({
    "quick-ask": ["Plan togetherCadence asks how you want to work, then sums up your answers.", "Paste the assignmentCadence proposes the goal, deliverables and milestones.", "Plan tasksList the tasks; Cadence suggests who could take each.", "Check-inCompare the plan with the dates and see what slips.", "Catch upWhat changed while you were away."],
    "quick-dates": ["TodayNothing due today.", "Day by dayEvery open task and milestone by date, late first.", "Edit tasksChange the owner, date or status of any task.", "Add to my calendarA private link for Google Calendar or Outlook."],
    "quick-memory": ["Ask whyWhy did the group decide something? Answered from the log.", "Refresh the planReload the plan if something looks out of date."],
    "quick-you": ["Your profileSkills and background: Cadence suggests owners from them.", "Show the tourThe quick walk-through of this screen."],
  });
  expect(within(panel).queryByRole("button", { name: /^(Create a )?(task|milestone)/i })).toBeNull();
});

test("the dates and memory shortcuts each open their own popup", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  for (const [button, title] of [[/^Today/, "Today"], [/^Day by day/, "Day by day"], [/^Edit tasks/, "Edit tasks"], [/^Add to my calendar/, "Add to my calendar"], [/^Ask why/, "Ask why"], [/^Your profile/, "Your profile"]] as const) {
    await userEvent.click(within(screen.getByRole("complementary", { name: "Quick access" })).getByRole("button", { name: button }));
    const popup = screen.getByRole("dialog", { name: title });
    expect(popup).toBeInTheDocument();
    (popup as HTMLDialogElement).close();
  }
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
  const page = screen.getByRole("region", { name: "Decisions" });
  expect(within(page).getByText(/No plan confirmed yet/)).toBeInTheDocument();
  expect(within(page).getByText(/No decision recorded yet/)).toBeInTheDocument();
});

test("the brief written while creating the space goes to Cadence once, as the usual kickoff", async () => {
  sessionStorage.setItem("cadence.brief:t-brief", "Deliver the prototype by 2 December.");
  render(<Console token="t-brief" onLeave={() => undefined} />);
  expect(await screen.findByText(/Cadence read your brief/)).toBeInTheDocument();
  expect(asked).toContainEqual({ type: "command", command: "kickoff", args: { text: "Deliver the prototype by 2 December." } });
  expect(sessionStorage.getItem("cadence.brief:t-brief")).toBeNull();
});

test("Connect Slack or Discord explains the bot and the link command", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(screen.getByRole("button", { name: "Connect Slack or Discord" }));
  const popup = screen.getByRole("dialog", { name: "Connect Slack or Discord" });
  expect(within(popup).getByText(/Without the bot installed, the command does nothing/)).toBeInTheDocument();
});

test("Plan together, from Quick access, asks the server with the approach command", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(screen.getByRole("button", { name: /^Plan together/ }));
  expect(asked).toContainEqual({ type: "command", command: "approach" });
});

test("below 1100px Quick access is a sheet: it starts closed, focus goes into it, and the page behind is inert until it closes", async () => {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: true, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false }));
  render(<Console token="t" onLeave={() => undefined} />);
  const toggle = screen.getByRole("button", { name: "Quick access" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("complementary", { name: "Quick access" })).toBeNull();

  await userEvent.click(toggle);
  expect(screen.getByRole("button", { name: "Close quick access" })).toHaveFocus();
  expect(document.querySelector(".console__main")).toHaveAttribute("inert");
  expect(document.querySelector(".side")).toHaveAttribute("inert");

  // A shortcut closes the sheet and opens its popup.
  await userEvent.click(screen.getByRole("button", { name: /^Ask why/ }));
  expect(screen.queryByRole("complementary", { name: "Quick access" })).toBeNull();
  expect(screen.getByRole("dialog", { name: "Ask why" })).toBeInTheDocument();
  expect(document.querySelector(".console__main")).not.toHaveAttribute("inert");
  vi.unstubAllGlobals();
});
