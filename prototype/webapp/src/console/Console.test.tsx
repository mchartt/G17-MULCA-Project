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

test("Delete this space is no longer next to the invite: it is under Space settings", () => {
  render(<Console token="t" onLeave={() => undefined} />);
  const del = screen.getByRole("button", { name: "Delete this space", hidden: true });
  expect(del.closest("details")).toHaveTextContent("Space settings");
});
