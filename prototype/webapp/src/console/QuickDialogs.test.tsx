import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { NewMilestoneDialog, NewTaskDialog, OwnersDialog, WaitsOnDialog } from "./QuickDialogs";

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

test("find owners: lists the open tasks nobody owns and asks Cadence for one card", async () => {
  const list = [
    { task_id: "a", title: "Build the API", status: "todo", owner_id: null, due_date: "2026-11-24" },
    { task_id: "b", title: "Slides", status: "doing", owner_id: 2, due_date: null },
    { task_id: "c", title: "Old thing", status: "done", owner_id: null, due_date: null },
  ];
  const onFind = vi.fn().mockResolvedValue("Cadence is busy.");
  render(<OwnersDialog open tasks={list} onClose={vi.fn()} onFind={onFind} />);
  const shown = screen.getByRole("list", { name: "Tasks with no owner" });
  expect(within(shown).getByText("Build the API")).toBeInTheDocument();
  expect(within(shown).queryByText("Slides")).toBeNull();
  expect(within(shown).queryByText("Old thing")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Ask Cadence to propose owners" }));
  expect(onFind).toHaveBeenCalled();
  expect(await screen.findByRole("alert")).toHaveTextContent("Cadence is busy.");
});

test("find owners: every task owned says so and asks nothing", () => {
  render(<OwnersDialog open tasks={[{ task_id: "b", title: "Slides", status: "todo", owner_id: 2 }]} onClose={vi.fn()} onFind={vi.fn()} />);
  expect(screen.getByText("Every open task already has an owner.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /propose owners/ })).toBeNull();
});

const linked = [
  { task_id: "a", title: "Build the API", status: "doing", owner_id: 1, due_date: null },
  { task_id: "d", title: "Design", status: "done", owner_id: 1, due_date: null },
  { task_id: "t", title: "Test the API", status: "todo", owner_id: 2, due_date: null, depends_on: ["a", "d"] },
  { task_id: "r", title: "Release", status: "todo", owner_id: 2, due_date: null },
];

test("link tasks: opened from a row, the task is chosen and what it waits on is already ticked, even a done one", async () => {
  const onSave = vi.fn().mockResolvedValue(null);
  render(<WaitsOnDialog open tasks={linked} taskId="t" onClose={vi.fn()} onSave={onSave} />);
  expect(screen.getByLabelText("Task")).toHaveValue("t");
  expect(screen.getByLabelText("Build the API")).toBeChecked();
  expect(screen.getByLabelText("Design")).toBeChecked(); // done, but linked: kept in the list
  expect(screen.queryByLabelText("Test the API", { selector: "input[type=checkbox]" })).toBeNull(); // a task cannot wait on itself
  await userEvent.click(screen.getByLabelText("Design"));
  await userEvent.click(screen.getByLabelText("Release"));
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(onSave).toHaveBeenCalledWith("t", ["a", "r"]);
});

test("link tasks: opened from the page, nothing is chosen until a task is; choosing one loads its links", async () => {
  const onSave = vi.fn().mockResolvedValue(null);
  render(<WaitsOnDialog open tasks={linked} taskId={null} onClose={vi.fn()} onSave={onSave} />);
  expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  await userEvent.selectOptions(screen.getByLabelText("Task"), "Release");
  await userEvent.click(screen.getByLabelText("Build the API"));
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(onSave).toHaveBeenCalledWith("r", ["a"]);
  await userEvent.selectOptions(screen.getByLabelText("Task"), "Test the API");
  expect(screen.getByLabelText("Build the API")).toBeChecked(); // its own links, not the previous task's
});

test("link tasks: clearing every box saves an empty list, and a loop refused by the server is shown", async () => {
  const onSave = vi.fn().mockResolvedValue("That would make a loop: the tasks would wait on each other and none could start.");
  render(<WaitsOnDialog open tasks={linked} taskId="t" onClose={vi.fn()} onSave={onSave} />);
  await userEvent.click(screen.getByLabelText("Build the API"));
  await userEvent.click(screen.getByLabelText("Design"));
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  expect(onSave).toHaveBeenCalledWith("t", []);
  expect(await screen.findByRole("alert")).toHaveTextContent("That would make a loop");
});
