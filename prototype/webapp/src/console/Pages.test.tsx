import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { MemberId } from "../lib/types";
import { DependenciesPage, MilestonesPage, ReflectionPage, TasksPage } from "./Pages";

// jsdom has no <dialog> modal: show it as open.
HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };

const task = (task_id: string, title: string, status = "todo", depends_on: string[] = [], owner_id: number | null = 1, due_date: string | null = null) => ({ task_id, title, status, depends_on, owner_id, due_date });

test("milestones: to complete, to schedule and date passed are three groups; a date moves one up, a click removes one", async () => {
  const onMilestone = vi.fn().mockResolvedValue(null);
  const milestones = [
    { milestone_id: "m1", title: "Demo Madness", due_date: "2026-12-02" },
    { milestone_id: "m2", title: "Report", due_date: null },
    { milestone_id: "m3", title: "Kickoff", due_date: "2026-11-10" },
  ];
  render(<MilestonesPage milestones={milestones} today="2026-11-19" onMilestone={onMilestone} onNew={vi.fn()} />);
  expect(within(screen.getByRole("region", { name: /^To complete/ })).getByText("Demo Madness")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: /^To schedule/ })).getByText("Report")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: /^Date passed/ })).getByText("Kickoff")).toBeInTheDocument();

  await userEvent.type(screen.getByLabelText("Date of Report"), "2026-12-01");
  expect(onMilestone).toHaveBeenLastCalledWith({ milestone: "m2", due: "2026-12-01" });
  await userEvent.click(screen.getByRole("button", { name: "Remove Kickoff" }));
  expect(onMilestone).toHaveBeenLastCalledWith({ milestone: "m3", remove: true });
});

test("milestones: creating goes through the popup, so the page only asks for it; empty says what to do", async () => {
  const onNew = vi.fn();
  render(<MilestonesPage milestones={[]} today="2026-11-19" onMilestone={vi.fn()} onNew={onNew} />);
  expect(screen.getByText(/No milestones yet/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "New milestone" }));
  expect(onNew).toHaveBeenCalled();
});

const names = (id?: MemberId | null) => (id === 1 ? "Ada" : id === 2 ? "Bruno" : undefined);
const members = [{ id: 1, name: "Ada" }, { id: 2, name: "Bruno" }];

test("dependencies: empty explains where a dependency comes from", async () => {
  const onNew = vi.fn();
  render(<DependenciesPage tasks={[task("a", "API")]} proposals={[]} nameOf={names} onNew={onNew} onLink={vi.fn()} onAnswer={vi.fn()} />);
  expect(screen.getByText(/Nothing waits on anything yet/)).toBeInTheDocument();
  await userEvent.click(screen.getAllByRole("button", { name: /New task/ })[0]!);
  expect(onNew).toHaveBeenCalled();
});

test("dependencies: every task is a note on the board, the waits are said in words, a note opens its links", async () => {
  const onLink = vi.fn();
  const tasks = [task("a", "Build the API"), task("b", "Test the API", "todo", ["a"], 2)];
  render(<DependenciesPage tasks={tasks} proposals={[]} nameOf={names} onNew={vi.fn()} onLink={onLink} onAnswer={vi.fn()} />);
  expect(screen.getByRole("button", { name: /^Build the API Ada To do/ })).toBeInTheDocument();
  expect(within(screen.getByRole("list", { name: "Test the API waits on" })).getByText(/Build the API/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /^Test the API Bruno Waiting/ }));
  expect(onLink).toHaveBeenCalledWith("b");
});

test("dependencies: Cadence's suggestion is shown with Confirm and Not now", async () => {
  const onAnswer = vi.fn();
  const proposal = { proposal_id: "p1", kind: "blocker", status: "pending", payload: { certainty: "possible", task_id: "b", depends_on_task_id: "a", question: "Does “Test the API” wait on “Build the API”? Tests need the API." } };
  render(
    <DependenciesPage tasks={[task("a", "Build the API"), task("b", "Test the API")]} proposals={[proposal as never]} nameOf={names} onNew={vi.fn()} onLink={vi.fn()} onAnswer={onAnswer} />,
  );
  const idea = within(screen.getByRole("list", { name: "Cadence's suggestions" }));
  expect(idea.getByText(/“Test the API” waits on “Build the API”/)).toBeInTheDocument();
  await userEvent.click(idea.getByRole("button", { name: "Confirm" }));
  expect(onAnswer).toHaveBeenCalledWith("p1", "confirm");
});

test("tasks: four tabs; Due soon holds late and near tasks; a row opens its details and progress is saved", async () => {
  const onTask = vi.fn();
  const tasks = [
    { ...task("a", "Late report", "todo", [], 1, "2026-11-10"), progress: 20 },
    { ...task("b", "Interviews", "doing", [], 2, "2026-11-22"), description: "Five students, think-aloud." },
    task("c", "Far away", "todo", [], null, "2026-12-30"),
    { ...task("d", "Recruit", "done"), done_at: 10 },
  ];
  render(<TasksPage tasks={tasks} members={members} today="2026-11-19" me={1} nameOf={names} onTask={onTask} onNew={vi.fn()} onLink={vi.fn()} />);
  expect(screen.getByRole("tab", { name: /Due soon 2/ })).toHaveAttribute("aria-selected", "true");
  const panel = within(screen.getByRole("tabpanel"));
  expect(panel.getByText("Late report")).toBeInTheDocument();
  expect(panel.getByText(/^Late ·/)).toBeInTheDocument();
  expect(panel.getByText("Five students, think-aloud.")).toBeInTheDocument();
  expect(panel.queryByText("Far away")).toBeNull();

  await userEvent.click(screen.getByRole("tab", { name: /To do 2/ }));
  await userEvent.click(within(screen.getByRole("tabpanel")).getByRole("button", { name: "I'll take it: Far away" }));
  expect(onTask).toHaveBeenLastCalledWith("c", { owner: 1 });

  await userEvent.click(screen.getByRole("tab", { name: /Completed 1/ }));
  expect(within(screen.getByRole("tabpanel")).getByText("Recruit")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: /In progress 1/ }));
  await userEvent.click(screen.getByRole("button", { name: /^Interviews .*Open the details$/ }));
  const dialog = within(screen.getByRole("dialog", { name: "Task details" }));
  fireEvent.change(dialog.getByLabelText(/Progress/), { target: { value: "20" } });
  await userEvent.click(dialog.getByRole("button", { name: "Save" }));
  expect(onTask).toHaveBeenLastCalledWith("b", { progress: 20 });
});

test("tasks: a very long title is cut in the row and whole in its details", async () => {
  const long = "A task with a title so long that it would push the owner and the date out of the row ".repeat(3).trim();
  render(<TasksPage tasks={[task("a", long, "todo", [], 1, "2026-11-20")]} members={members} today="2026-11-19" me={1} nameOf={names} onTask={vi.fn()} onNew={vi.fn()} onLink={vi.fn()} />);
  expect(screen.getByTitle(long)).toHaveClass("task-card__title");
  await userEvent.click(screen.getByRole("button", { name: new RegExp(`^${long}.*Open the details$`) }));
  expect(screen.getByLabelText("Title")).toHaveValue(long);
});

test("reflection: the week in numbers and topics, group-level, from the server", async () => {
  const week = {
    week: "2026-11-16", until: "2026-11-22", current: true,
    done: [{ task_id: "a", title: "Recruit 5 participants" }], added: [], slipped: [{ task_id: "b", title: "Slides", due_date: "2026-11-18" }],
    decisions: [{ decision_id: "d1", question: "Which test?", choice: "Think-aloud", at: 1 }],
    upcoming: [{ milestone_id: "m1", title: "Demo Madness", due_date: "2026-12-02" }],
    talk: [{ channel: "web", messages: 12 }, { channel: "discord", messages: 5 }],
    progress: { done: 1, total: 4 },
    topics: [{ title: "Lab booking", summary: "The group agreed on Tuesday at 17:00." }],
  };
  const onLoad = vi.fn().mockResolvedValue(week);
  render(<ReflectionPage state={null} today="2026-11-19" nameOf={names} onLoad={onLoad} />);
  expect(await screen.findByText("Lab booking")).toBeInTheDocument();
  expect(onLoad).toHaveBeenCalledWith("2026-11-16");
  const stats = within(screen.getByRole("list", { name: "The week in numbers" }));
  expect(stats.getByText("17")).toBeInTheDocument();
  expect(stats.getByText("25%")).toBeInTheDocument();
  expect(screen.getByText("Recruit 5 participants")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next week" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Previous week" }));
  expect(onLoad).toHaveBeenLastCalledWith("2026-11-09");
});

test("reflection: an error from the server is said", async () => {
  render(<ReflectionPage state={null} today="2026-11-19" nameOf={names} onLoad={vi.fn().mockResolvedValue("Cadence is not available.")} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Cadence is not available.");
});
