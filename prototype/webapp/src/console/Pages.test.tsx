import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { DependenciesPage, MilestonesPage, ReflectionPage } from "./Pages";

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

test("dependencies: empty explains where a dependency comes from", async () => {
  const onNew = vi.fn();
  render(<DependenciesPage tasks={[task("a", "API")]} onNew={onNew} />);
  expect(screen.getByText(/Nothing waits on anything yet/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "New task" }));
  expect(onNew).toHaveBeenCalled();
});

test("dependencies: each task that waits shows what it needs, and whether it can start", () => {
  const tasks = [task("a", "Build the API", "doing"), task("d", "Design", "done"), task("t", "Test the API", "todo", ["a"]), task("r", "Release", "todo", ["d"])];
  render(<DependenciesPage tasks={tasks} onNew={vi.fn()} />);
  const testing = screen.getByText("Test the API").closest("li")!;
  expect(within(testing).getByText("Waiting")).toBeInTheDocument();
  expect(within(within(testing).getByRole("list", { name: "Test the API waits on" })).getByText("Build the API")).toBeInTheDocument();
  const release = screen.getByText("Release").closest("li")!;
  expect(within(release).getByText("Ready to start")).toBeInTheDocument();
});

test("reflection: counts from the plan, only the ones that matter, and the decisions with their reasons", () => {
  const state = {
    tasks: [task("a", "A", "done"), task("b", "B", "todo", [], null, "2026-11-10"), task("c", "C", "todo", [], 1, null)],
    milestones: [{ milestone_id: "m", title: "Demo", due_date: null }],
    decisions: [{ question: "Which database?", choice: "SQLite", reason: "No server to run" }, { question: "Poster size?", choice: "A1" }],
  };
  render(<ReflectionPage state={state} today="2026-11-19" />);
  expect(screen.getByText("of 3 tasks done", { exact: false })).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "Tasks done" })).toHaveAttribute("value", "1");
  expect(screen.getByText("tasks are late", { exact: false })).toBeInTheDocument();
  expect(screen.getByText("open tasks have no owner", { exact: false })).toBeInTheDocument();
  expect(screen.queryByText("milestone dates have passed", { exact: false })).toBeNull(); // zero: not shown
  expect(screen.getByText("Which database?")).toBeInTheDocument();
  expect(screen.getByText(/No server to run/)).toBeInTheDocument();
  expect(screen.getByText("A1")).toBeInTheDocument();
});

test("reflection: nothing saved yet says so, without numbers", () => {
  render(<ReflectionPage state={null} today="2026-11-19" />);
  expect(screen.getByText("No tasks yet.")).toBeInTheDocument();
  expect(screen.getByText(/No decision recorded yet/)).toBeInTheDocument();
});
