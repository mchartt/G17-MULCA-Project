import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { NewMilestoneDialog, NewTaskDialog, TodayDialog } from "./QuickDialogs";

// jsdom has no <dialog> modal: show it as open.
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };

const members = [{ id: 1, name: "Ada" }, { id: 2, name: "Bruno" }];
const tasks = [
  { task_id: "a", title: "Server API", status: "doing", owner_id: 1, due_date: "2026-11-18" },
  { task_id: "b", title: "Slides", status: "todo", owner_id: null, due_date: null },
  { task_id: "c", title: "Kickoff notes", status: "done", owner_id: 2, due_date: null },
];

test("new task: the Add button waits for a name, then sends name, description, owner, date and what it waits on", async () => {
  const onCreate = vi.fn().mockResolvedValue(null);
  render(<NewTaskDialog open tasks={tasks} members={members} onClose={vi.fn()} onCreate={onCreate} />);
  expect(screen.getByRole("button", { name: "Add task" })).toBeDisabled();

  await userEvent.type(screen.getByLabelText("Name"), "Test the API");
  await userEvent.type(screen.getByLabelText("Description (optional)"), "Run the contract tests");
  await userEvent.selectOptions(screen.getByLabelText("Owner"), "Bruno");
  await userEvent.type(screen.getByLabelText("Due date"), "2026-11-25");
  await userEvent.click(screen.getByLabelText("Server API"));
  await userEvent.click(screen.getByRole("button", { name: "Add task" }));

  expect(onCreate).toHaveBeenCalledWith({ title: "Test the API", description: "Run the contract tests", owner: 2, due: "2026-11-25", waitsOn: ["a"] });
});

test("new task: it can wait only on open tasks, and a task with nothing else is created with the bare minimum", async () => {
  const onCreate = vi.fn().mockResolvedValue(null);
  render(<NewTaskDialog open tasks={tasks} members={members} onClose={vi.fn()} onCreate={onCreate} />);
  const waits = screen.getByRole("group", { name: "Waits on (optional)" });
  expect(within(waits).getAllByRole("checkbox").map((box) => (box as HTMLInputElement).labels?.[0]?.textContent)).toEqual(["Server API", "Slides"]); // the done one is left out

  await userEvent.type(screen.getByLabelText("Name"), "  Poster ");
  await userEvent.click(screen.getByRole("button", { name: "Add task" }));
  expect(onCreate).toHaveBeenCalledWith({ title: "Poster", description: "", owner: null, due: null, waitsOn: [] });
});

test("new task: with no other task there is nothing to wait on, and the popup says so", () => {
  render(<NewTaskDialog open tasks={[]} members={members} onClose={vi.fn()} onCreate={vi.fn()} />);
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(screen.getByText("No other open task yet.")).toBeInTheDocument();
});

test("new task: a refusal from the server is shown in the popup and what was typed stays", async () => {
  const onCreate = vi.fn().mockResolvedValue("That would make a loop: the tasks would wait on each other and none could start.");
  render(<NewTaskDialog open tasks={tasks} members={members} onClose={vi.fn()} onCreate={onCreate} />);
  await userEvent.type(screen.getByLabelText("Name"), "Test the API");
  await userEvent.click(screen.getByRole("button", { name: "Add task" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("That would make a loop");
  expect(screen.getByLabelText("Name")).toHaveValue("Test the API");
});

test("new task: the popup starts empty every time it opens", async () => {
  const props = { tasks, members, onClose: vi.fn(), onCreate: vi.fn().mockResolvedValue(null) };
  const { rerender } = render(<NewTaskDialog open {...props} />);
  await userEvent.type(screen.getByLabelText("Name"), "Draft");
  await userEvent.click(screen.getByLabelText("Slides"));
  rerender(<NewTaskDialog open={false} {...props} />);
  rerender(<NewTaskDialog open {...props} />);
  expect(screen.getByLabelText("Name")).toHaveValue("");
  expect(screen.getByLabelText("Slides")).not.toBeChecked();
});

test("new milestone: a name and an optional date; the date can be left for later", async () => {
  const onCreate = vi.fn().mockResolvedValue(null);
  render(<NewMilestoneDialog open onClose={vi.fn()} onCreate={onCreate} />);
  expect(screen.getByRole("button", { name: "Add milestone" })).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Name"), "Prototype ready");
  await userEvent.click(screen.getByRole("button", { name: "Add milestone" }));
  expect(onCreate).toHaveBeenCalledWith({ add: "Prototype ready", due: null });

  await userEvent.type(screen.getByLabelText("Name"), "Report");
  await userEvent.type(screen.getByLabelText("Date (optional)"), "2026-12-01");
  await userEvent.click(screen.getByRole("button", { name: "Add milestone" }));
  expect(onCreate).toHaveBeenLastCalledWith({ add: "Report", due: "2026-12-01" });
});

test("today: what is late and what is due today, with who has it; open tasks without a date are not shown", () => {
  const list = [
    ...tasks,
    { task_id: "d", title: "User test", status: "todo", owner_id: 2, due_date: "2026-11-19" },
    { task_id: "e", title: "Report", status: "todo", owner_id: 1, due_date: "2026-12-01" },
  ];
  const nameOf = (id?: number | string | null) => members.find((m) => m.id === id)?.name;
  render(<TodayDialog open today="2026-11-19" tasks={list} nameOf={nameOf} onTask={vi.fn()} onClose={vi.fn()} />);
  const late = screen.getByRole("region", { name: "Late" });
  expect(within(late).getByText("Server API")).toBeInTheDocument();
  const today = screen.getByRole("region", { name: "Due today" });
  expect(within(today).getByText("User test")).toBeInTheDocument();
  expect(within(today).getByText("Bruno")).toBeInTheDocument();
  expect(screen.queryByText("Report")).toBeNull();
  expect(screen.queryByText("Slides")).toBeNull();
});

test("today: nothing due says so", () => {
  render(<TodayDialog open today="2026-11-19" tasks={tasks.slice(1)} nameOf={() => undefined} onTask={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByText("Nothing is due today and nothing is late.")).toBeInTheDocument();
});
