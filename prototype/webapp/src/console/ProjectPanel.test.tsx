import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProjectPanel } from "./ProjectPanel";

const members = [{ id: 1, name: "Ada" }, { id: 2, name: "Bruno" }];

test("with no charter the panel invites to paste the assignment", async () => {
  const onKickoff = vi.fn();
  render(<ProjectPanel state={null} members={members} onKickoff={onKickoff} onRefresh={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Paste the assignment" }));
  expect(onKickoff).toHaveBeenCalled();
});

test("the panel shows goal, who confirmed it, milestones, tasks with owners and decisions", () => {
  render(
    <ProjectPanel
      state={{
        charter: { goal: "Ship the coordinator.", confirmed_by: 1 },
        milestones: [{ title: "Demo", due_date: "2026-12-02" }],
        tasks: [{ title: "User test", status: "open", owner_id: 2 }, { title: "Slides", status: "proposed", owner_id: null }],
        decisions: [{ question: "Which channel first?", choice: "Web and Discord", reason: "The course already uses Discord." }],
      }}
      members={members}
      onKickoff={vi.fn()}
      onRefresh={vi.fn()}
    />,
  );
  expect(screen.getByText("Ship the coordinator.")).toBeInTheDocument();
  expect(screen.getByText("Confirmed by Ada")).toBeInTheDocument();
  expect(screen.getByText("Demo")).toBeInTheDocument();
  expect(screen.getByText("Bruno")).toBeInTheDocument();
  expect(screen.getByText("No owner")).toBeInTheDocument();
  expect(screen.getByText("Web and Discord")).toBeInTheDocument();
});

test("empty sections say what is missing", () => {
  render(<ProjectPanel state={{ charter: { goal: "G" } }} members={members} onKickoff={vi.fn()} onRefresh={vi.fn()} />);
  expect(screen.getByText("No milestones yet.")).toBeInTheDocument();
  expect(screen.getByText(/No tasks yet/)).toBeInTheDocument();
  expect(screen.getByText("No decisions recorded yet.")).toBeInTheDocument();
});
