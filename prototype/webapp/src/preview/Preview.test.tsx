import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../App";
import { CatchUp } from "./CatchUp";
import { Connections } from "./Connections";
import { PlanWeek } from "./PlanWeek";
import { Preview, viewFromPath } from "./Preview";
import { Reflection } from "./Reflection";
import { BUSY, MEETING_SLOTS, freeForAll, freeHours } from "./sample";

beforeAll(() => {
  window.scrollTo = vi.fn();
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => history.replaceState(null, "", "/"));

test("a path under /preview picks its screen, an unknown one the first", () => {
  expect(viewFromPath("/preview/plan")).toBe("plan");
  expect(viewFromPath("/preview/catch-up/")).toBe("catch-up");
  expect(viewFromPath("/preview")).toBe("connections");
  expect(viewFromPath("/preview/nothing")).toBe("connections");
});

test("the app shows the preview under /preview, with no space and no token", () => {
  history.replaceState(null, "", "/preview/reflection");
  render(<App />);
  expect(screen.getByRole("heading", { level: 1, name: "How the project went." })).toBeInTheDocument();
  expect(screen.getByText("Preview · sample data")).toBeInTheDocument();
});

test("the tabs change the screen and the address", async () => {
  history.replaceState(null, "", "/preview");
  render(<Preview />);
  await userEvent.click(screen.getByRole("link", { name: "Catch up" }));
  expect(location.pathname).toBe("/preview/catch-up");
  expect(screen.getByRole("heading", { level: 1, name: "Miss a call, not a decision." })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Catch up" })).toHaveAttribute("aria-current", "page");
});

test("the free hours are the ones in which no member is busy", () => {
  expect(freeForAll({ 1: [[0, 9, 12]], 2: [[0, 11, 18]] }, 1)).toEqual([{ day: 0, from: 18, to: 19 }]);
  expect(freeForAll({ 1: [] }, 1)).toEqual([{ day: 0, from: 9, to: 19 }]);
  // The sample week: one shared hour on each day before the draft.
  expect(MEETING_SLOTS).toEqual([{ day: 0, from: 18, to: 19 }, { day: 1, from: 17, to: 19 }, { day: 2, from: 14, to: 15 }]);
  for (const slot of freeForAll(BUSY)) {
    for (const blocks of Object.values(BUSY)) {
      expect(blocks.some(([day, from, to]) => day === slot.day && slot.from < to && slot.to > from)).toBe(false);
    }
  }
  expect(freeHours(BUSY[2])).toBe(10);
});

test("connecting a source changes its status in words, the web space cannot be disconnected", async () => {
  render(<Connections />);
  expect(screen.queryByRole("button", { name: /Cadence web space/ })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Connect Slack" }));
  expect(screen.getByRole("button", { name: "Disconnect Slack" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Disconnect Google Calendar" }));
  expect(screen.getByRole("button", { name: "Connect Google Calendar" })).toBeInTheDocument();
});

test("the meeting is added to the plan only when a member picks an hour", async () => {
  render(<PlanWeek />);
  expect(screen.queryByText(/Added to the plan/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Tue 17:00" }));
  expect(screen.getByText(/Added to the plan: report meeting, Tue 17:00–19:00/)).toBeInTheDocument();
  expect(screen.getByText("Confirmed")).toBeInTheDocument();
  expect(screen.getByText("17:00–19:00 · chosen")).toBeInTheDocument();
});

test("Not now changes nothing in the plan", async () => {
  render(<PlanWeek />);
  await userEvent.click(screen.getByRole("button", { name: "Not now" }));
  expect(screen.queryByText(/Added to the plan/)).not.toBeInTheDocument();
  expect(screen.getByText(/silenced on this topic/)).toBeInTheDocument();
});

test("the catch-up names what was missed with its source, and the task waits for a click", async () => {
  render(<CatchUp />);
  expect(screen.getByText(/Source: Discord call, Thu 19 Nov, 18:12/)).toBeInTheDocument();
  const monday = screen.getByRole("region", { name: /Monday 23 Nov/ });
  expect(within(monday).getByText("Waiting for a member to confirm")).toBeInTheDocument();
  await userEvent.click(within(monday).getByRole("button", { name: "Confirm" }));
  expect(within(monday).getByText("Confirmed")).toBeInTheDocument();
});

test("the reflection is saved only after a member keeps a point and confirms", async () => {
  render(<Reflection />);
  const save = screen.getByRole("button", { name: "Save the reflection" });
  expect(save).toBeDisabled();
  const point = screen.getByRole("button", { name: "Agree a report template before anyone writes" });
  await userEvent.click(point);
  expect(point).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText(/1 of 5 points kept. Nothing is saved/)).toBeInTheDocument();
  await userEvent.click(save);
  expect(screen.getByText("Saved: 1 of 5 points kept, confirmed by Ada.")).toBeInTheDocument();
  expect(screen.getByText("3 days late")).toBeInTheDocument();
});
