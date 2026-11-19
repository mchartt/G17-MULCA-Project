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

test("the console opens chat first: the plan is closed and there is one menu instead of five buttons", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  expect(screen.getByRole("region", { name: "Group chat" })).toBeInTheDocument();
  const plan = screen.getByRole("button", { name: "Plan" });
  expect(plan).toHaveAttribute("aria-expanded", "false");
  expect(document.getElementById("plan")).toBeNull();
  const bar = screen.getByRole("banner");
  expect(within(bar).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual(["Ask Cadence", "Plan"]);

  await userEvent.click(plan);
  expect(plan).toHaveAttribute("aria-expanded", "true");
  expect(document.getElementById("plan")).not.toBeNull();
});

test("Check-in from the Ask Cadence menu runs the same command as before", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(screen.getByRole("button", { name: "Ask Cadence" }));
  await userEvent.click(screen.getByRole("menuitem", { name: /^Check-in/ }));
  expect(asked).toContainEqual({ type: "command", command: "checkin" });
  expect(await screen.findByText("On track.")).toBeInTheDocument();
});

test("Delete this space is no longer next to the invite: it is under Project settings", () => {
  render(<Console token="t" onLeave={() => undefined} />);
  const del = screen.getByRole("button", { name: "Delete this space", hidden: true });
  expect(del.closest("details")).toHaveTextContent("Project settings");
});

test("the Task quick action opens a popup; the task goes out as the usual task command and the popup closes when it is accepted", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(within(screen.getByRole("navigation", { name: "Quick actions" })).getByRole("button", { name: "Create a task" }));
  const popup = screen.getByRole("dialog", { name: "New task" });
  await userEvent.type(within(popup).getByLabelText("Name"), "Test the API");
  await userEvent.type(within(popup).getByLabelText("Description (optional)"), "Contract tests");
  await userEvent.click(within(popup).getByRole("button", { name: "Add task" }));
  expect(asked).toContainEqual({ type: "command", command: "task", args: { add: "Test the API", owner: "", due: "", description: "Contract tests" } });
  expect(await screen.findByText("Task added: “Test the API”.")).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "New task" })).toBeNull();
});

test("the Milestone quick action makes a milestone, in its own popup", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(screen.getByRole("button", { name: "Create a milestone" }));
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

test("a page's New button opens the same popup as the Task quick action", async () => {
  render(<Console token="t" onLeave={() => undefined} />);
  await userEvent.click(within(screen.getByRole("list", { name: "Pages" })).getByRole("button", { name: "Dependencies" }));
  await userEvent.click(screen.getByRole("button", { name: "New task" }));
  expect(screen.getByRole("dialog", { name: "New task" })).toBeInTheDocument();
});

test("the quick actions sit on the right: task, milestone, today, profile, tour", () => {
  render(<Console token="t" onLeave={() => undefined} />);
  const rail = screen.getByRole("navigation", { name: "Quick actions" });
  expect(within(rail).getAllByRole("button").map((b) => b.getAttribute("aria-label"))).toEqual([
    "Create a task", "Create a milestone", "Today: nothing due", "Your profile", "Show the tour again",
  ]);
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
