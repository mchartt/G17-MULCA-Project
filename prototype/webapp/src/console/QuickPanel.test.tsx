import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { faBolt } from "../lib/icons";
import { todayIso } from "./plan";
import { QuickPanel, todaySummary } from "./QuickPanel";

// jsdom has no <dialog> modal: show it as open.
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };

test("the panel says what it is, groups its buttons, and each button says what it does", async () => {
  const run = vi.fn();
  const onClose = vi.fn();
  render(
    <QuickPanel
      onClose={onClose}
      groups={[
        { key: "ask", title: "Ask Cadence", note: "For when you want it to.", tone: "cadence", entries: [{ key: "checkin", label: "Check-in", about: "Compare the plan with the dates.", icon: faBolt, run }] },
        { key: "dates", title: "Your dates", entries: [{ key: "today", label: "Today", about: "2 due.", icon: faBolt, badge: 2, run: vi.fn() }] },
      ]}
    />,
  );
  expect(screen.getByRole("complementary", { name: "Quick access" })).toBeInTheDocument();
  const ask = screen.getByRole("region", { name: "Ask Cadence" });
  // The name is the visible text: the label, then its line of help.
  await userEvent.click(within(ask).getByRole("button", { name: "Check-in Compare the plan with the dates." }));
  expect(run).toHaveBeenCalled();
  expect(within(screen.getByRole("region", { name: "Your dates" })).getByRole("button", { name: "Today 2 due." })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Hide quick access" }));
  expect(onClose).toHaveBeenCalledTimes(1);
});

test("Escape inside the panel closes it", async () => {
  const onClose = vi.fn();
  render(<QuickPanel onClose={onClose} groups={[{ key: "g", title: "G", entries: [{ key: "a", label: "A", about: "a", icon: faBolt, run: vi.fn() }] }]} />);
  screen.getByRole("button", { name: "A a" }).focus();
  await userEvent.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalled();
});

test("Today says what is due and what is late, or that nothing is", () => {
  // Local days, as todayIso() counts them.
  const day = (offset: number) => {
    const [y, m, d] = todayIso().split("-").map(Number);
    const t = new Date(y!, m! - 1, d! + offset);
    return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
  };
  const task = (due_date: string | null) => ({ task_id: String(due_date), title: "T", status: "todo", owner_id: 1, due_date });
  expect(todaySummary([task(null)])).toEqual({ about: "Nothing due today.", count: 0 });
  const some = todaySummary([task(day(-3)), task(day(0))]);
  expect(some.count).toBe(2);
  expect(some.about).toMatch(/^1 due, 1 late/);
});
