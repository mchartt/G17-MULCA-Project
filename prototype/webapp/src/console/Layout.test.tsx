import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { Capped } from "./Capped";
import { WaitsOnDialog } from "./QuickDialogs";
import { Sidebar } from "./Sidebar";
import { emptySpace, type Space } from "./space";
import { Toast } from "./Toast";

// jsdom has no <dialog> modal: show it as open.
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };

// 20/11 (Matteo): nothing on a page may grow until the page scrolls; long things open in a popup.

test("a long list shows its first items and the rest in a popup", async () => {
  const items = ["A", "B", "C", "D", "E", "F"];
  render(<Capped label="Tasks" className="x" limit={4} title="All tasks" items={items} render={(t) => <li key={t}>{t}</li>} />);
  expect(within(screen.getByRole("list", { name: "Tasks" })).getAllByRole("listitem")).toHaveLength(4);
  expect(screen.queryByText("F")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "See all 6" }));
  expect(within(screen.getByRole("dialog", { name: "All tasks" })).getByText("F")).toBeInTheDocument();
});

test("Cadence's answer is a toast: two lines, Read all for long text, gone by itself unless held", async () => {
  vi.useFakeTimers();
  const onClose = vi.fn();
  render(<Toast text={"Task added: “ciao”. ".repeat(12)} onClose={onClose} />);
  const toast = screen.getByRole("status");
  expect(within(toast).getByRole("button", { name: "Read all" })).toHaveAttribute("aria-expanded", "false");
  act(() => { vi.advanceTimersByTime(7100); });
  expect(onClose).toHaveBeenCalledTimes(1);
  vi.useRealTimers();
});

test("link tasks: what it waits on shows as chips that can be removed, and the list can be searched", async () => {
  const tasks = [
    { task_id: "t", title: "Test the API", status: "todo", owner_id: 1, due_date: null, depends_on: ["a"] },
    ...["Build the API", "Design", "Mockup", "Slides", "Report", "Video"].map((title, i) => ({ task_id: i ? `x${i}` : "a", title, status: "todo", owner_id: 1, due_date: null })),
  ];
  const onSave = vi.fn().mockResolvedValue(null);
  render(<WaitsOnDialog open tasks={tasks} taskId="t" onClose={vi.fn()} onSave={onSave} />);
  const chips = screen.getByRole("list", { name: "It waits on" });
  expect(chips).toHaveTextContent("Build the API");
  await userEvent.type(screen.getByRole("searchbox", { name: "Find a task" }), "slid");
  expect(screen.getByLabelText("Slides")).toBeInTheDocument();
  expect(screen.queryByLabelText("Design")).toBeNull();
  await userEvent.click(screen.getByLabelText("Slides"));
  await userEvent.click(within(chips).getByRole("button", { name: "Remove Build the API" }));
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(onSave).toHaveBeenCalledWith("t", ["x3"]);
});

test("the rail shows three members; the whole team opens in a popup with a search", async () => {
  const names = ["Matteo", "Marco", "Mario", "Giulia", "Bruno", "Ada", "Chiara", "Dario"];
  const space: Space = { ...emptySpace, me: { id: 1, name: "Matteo" }, members: names.map((name, i) => ({ id: i + 1, name })), group: { id: 1, name: "G17", inviteCode: "T3W4JTT8AY" } } as Space;
  const onMember = vi.fn();
  render(<Sidebar space={space} view="chat" onView={vi.fn()} onLeave={vi.fn()} onSettings={vi.fn()} onMember={onMember} onConnect={vi.fn()} />);
  expect(screen.getByRole("button", { name: /Mario/ })).toBeInTheDocument(); // the third
  expect(screen.queryByRole("button", { name: /Giulia/ })).toBeNull(); // the fourth is only in the popup
  await userEvent.click(screen.getByRole("button", { name: /See all 8/ }));
  const popup = screen.getByRole("dialog", { name: "Members (8)" });
  await userEvent.type(within(popup).getByRole("searchbox", { name: "Find a member" }), "dar");
  await userEvent.click(within(popup).getByRole("button", { name: /Dario/ }));
  expect(onMember).toHaveBeenCalledWith(8);
  expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
});
