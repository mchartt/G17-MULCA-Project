import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { KickoffDialog } from "./Dialogs";
import { AgendaDialog, PlanningDialog, TaskRegisterDialog } from "./PlanDialogs";
import { TagInput, withPending } from "./TagInput";
import { useState } from "react";

// jsdom has no <dialog> modal: show it as open.
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };

const members = [{ id: 1, name: "Ada" }, { id: 2, name: "Bruno" }];
const nameOf = (id?: number | string | null) => members.find((m) => m.id === id)?.name;
const tasks = [
  { task_id: "a", title: "Server API", status: "doing", owner_id: 1, due_date: "2099-11-20" },
  { task_id: "b", title: "Slides", status: "todo", owner_id: null, due_date: null },
  { task_id: "c", title: "Kickoff notes", status: "done", owner_id: 2, due_date: null },
];

test("planning is a list: a chosen owner is kept, a row without one is for Cadence, empty rows are dropped", async () => {
  const onSend = vi.fn().mockResolvedValue(null);
  render(<PlanningDialog open members={members} onClose={vi.fn()} onSend={onSend} />);
  expect(screen.getByRole("button", { name: "Suggest owners" })).toBeDisabled(); // nothing written yet
  await userEvent.type(screen.getByLabelText("Task 1"), "Server API");
  await userEvent.selectOptions(screen.getByLabelText("Owner of task 1"), "Bruno");
  expect(screen.getByRole("button", { name: "Make the plan card" })).toBeEnabled(); // every owner chosen: nothing to suggest
  await userEvent.type(screen.getByLabelText("Task 2"), "User test");
  await userEvent.click(screen.getByRole("button", { name: "Suggest owners" }));
  expect(onSend).toHaveBeenCalledWith([
    { title: "Server API", owner: 2, due: null },
    { title: "User test", owner: null, due: null },
  ]);
});

test("planning: several lines pasted become one row each, and Enter on the last row adds one", async () => {
  render(<PlanningDialog open members={members} onClose={vi.fn()} onSend={vi.fn()} />);
  await userEvent.click(screen.getByLabelText("Task 1"));
  await userEvent.paste("Server API\nUI screens; User test");
  expect(screen.getByLabelText("Task 1")).toHaveValue("Server API");
  expect(screen.getByLabelText("Task 3")).toHaveValue("User test");
  const last = screen.getAllByRole("textbox").length;
  await userEvent.type(screen.getByLabelText(`Task ${last}`), "One more{Enter}");
  expect(screen.getAllByRole("textbox")).toHaveLength(last + 1);
});

test("the register shows every task and lets a member add, assign, date, close and remove one", async () => {
  const onTask = vi.fn();
  const onAdd = vi.fn().mockResolvedValue(null);
  render(<TaskRegisterDialog open tasks={tasks} members={members} me={2} nameOf={nameOf} onTask={onTask} onAdd={onAdd} onClose={vi.fn()} />);
  expect(screen.getAllByRole("listitem").map((li) => within(li).getByText(/Server API|Slides|Kickoff notes/).textContent)).toEqual(["Server API", "Slides"]); // open by default

  await userEvent.selectOptions(screen.getByLabelText("Owner of Slides"), "Ada");
  expect(onTask).toHaveBeenLastCalledWith("b", { owner: 1 });
  await userEvent.selectOptions(screen.getByLabelText("Owner of Server API"), "No owner");
  expect(onTask).toHaveBeenLastCalledWith("a", { owner: null });
  await userEvent.click(screen.getByRole("checkbox", { name: "Slides: done" }));
  expect(onTask).toHaveBeenLastCalledWith("b", { status: "done" });
  await userEvent.selectOptions(screen.getByLabelText("Status of Server API"), "blocked");
  expect(onTask).toHaveBeenLastCalledWith("a", { status: "blocked" });

  // Removing asks once more, in place.
  await userEvent.click(screen.getByRole("button", { name: "Remove Slides" }));
  expect(onTask).not.toHaveBeenCalledWith("b", { remove: true });
  await userEvent.click(screen.getByRole("button", { name: "Remove" }));
  expect(onTask).toHaveBeenLastCalledWith("b", { remove: true });

  await userEvent.click(screen.getByRole("button", { name: "Done" }));
  expect(screen.getByText("Kickoff notes")).toBeInTheDocument();
  expect(screen.queryByText("Slides")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Mine" }));
  expect(screen.getAllByRole("listitem")).toHaveLength(1);

  await userEvent.type(screen.getByLabelText("New task"), "Write the report");
  await userEvent.selectOptions(screen.getByLabelText("Owner of the new task"), "Bruno");
  await userEvent.click(screen.getByRole("button", { name: "Add task" }));
  expect(onAdd).toHaveBeenCalledWith({ title: "Write the report", owner: 2, due: null });
  expect(screen.getByLabelText("New task")).toHaveValue("");
});

test("day by day groups the open work and says who has it", () => {
  render(<AgendaDialog open tasks={tasks} milestones={[{ milestone_id: "m", title: "Demo", due_date: "2099-11-20" }]} members={members} nameOf={nameOf} onTask={vi.fn()} onClose={vi.fn()} />);
  const day = screen.getByRole("heading", { name: "Fri 20 Nov" }).closest("li")!;
  expect(day).toHaveTextContent("Demo");
  expect(day).toHaveTextContent("Server API");
  expect(day).toHaveTextContent("Ada");
  const undated = screen.getByRole("heading", { name: "No date yet" }).closest("li")!;
  expect(undated).toHaveTextContent("Slides");
  expect(undated).toHaveTextContent("No owner");
  expect(screen.queryByText("Kickoff notes")).toBeNull(); // done
});

test("skills are tags: Enter or a comma adds one, Backspace and the × remove, typed text still counts", async () => {
  function Field() {
    const [tags, setTags] = useState<string[]>(["Figma"]);
    return <><label htmlFor="s">Skills</label><TagInput id="s" tags={tags} onChange={setTags} /><output>{tags.join("|")}</output></>;
  }
  render(<Field />);
  const box = screen.getByLabelText("Skills");
  await userEvent.type(box, "User research{Enter}python,");
  expect(screen.getByRole("status")).toHaveTextContent("Figma|User research|python");
  await userEvent.type(box, "figma{Enter}"); // already there, whatever the case
  await userEvent.type(box, "{Backspace}");
  expect(screen.getByRole("status")).toHaveTextContent("Figma|User research");
  await userEvent.click(screen.getByRole("button", { name: "Remove Figma" }));
  expect(screen.getByRole("status")).toHaveTextContent("User research");
  expect(withPending(["A"], " b , a,, C ")).toEqual(["A", "b", "C"]);
});

test("the assignment can come from a document: its text lands in the box, still editable", async () => {
  const onRead = vi.fn().mockResolvedValueOnce({ name: "brief.pdf", text: "Build a coordinator.", truncated: false }).mockRejectedValueOnce(new Error("No text could be read from this file."));
  const onSend = vi.fn().mockResolvedValue(null);
  render(<KickoffDialog open onClose={vi.fn()} onSend={onSend} onRead={onRead} />);
  const file = new File(["%PDF"], "brief.pdf", { type: "application/pdf" });
  await userEvent.upload(screen.getByLabelText("Upload a document"), file);
  expect(await screen.findByDisplayValue("Build a coordinator.")).toBeInTheDocument();
  expect(screen.getByText(/Read from brief.pdf/)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Assignment"), " Demo on 2 Dec.");
  await userEvent.upload(screen.getByLabelText("Upload a document"), new File(["x"], "scan.pdf", { type: "application/pdf" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("No text could be read");
  await userEvent.click(screen.getByRole("button", { name: "Send to Cadence" }));
  expect(onSend).toHaveBeenCalledWith("Build a coordinator. Demo on 2 Dec.");
});
