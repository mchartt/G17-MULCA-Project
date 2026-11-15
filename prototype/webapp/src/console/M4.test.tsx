import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Proposal } from "../lib/types";
import { ProjectPanel } from "./ProjectPanel";
import { ProposalCard } from "./ProposalCard";

const names = (id: number) => ({ 1: "Ada", 2: "Bruno" })[id] ?? "?";

test("a plan card lists every task with the suggested owner and reason, confirmed with one click", async () => {
  const plan: Proposal = {
    proposal_id: "b1", kind: "plan", status: "pending", rationale: "Stepping in because you listed the tasks.",
    payload: { items: [{ title: "Server", owner_id: 1, reason: "Python skills", due_date: "2026-11-28" }, { title: "Slides", owner_id: null }] },
  };
  const onAnswer = vi.fn().mockResolvedValue({ type: "notice", ok: true, text: "Plan saved." });
  render(<ProposalCard proposal={plan} agentName="Cadence" onAnswer={onAnswer} memberName={names} />);
  expect(screen.getByRole("heading", { name: "Plan: who does what" })).toBeInTheDocument();
  expect(screen.getByText("Ada · 28 Nov · Python skills")).toBeInTheDocument();
  expect(screen.getByText("anyone")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Why?" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
  expect(onAnswer).toHaveBeenCalledWith({ action: "confirm" });
});

test("a check-in card shows the findings and one button per option", async () => {
  const checkin: Proposal = {
    proposal_id: "c2", kind: "checkin", status: "pending",
    payload: { findings: ["Late: “Server” (Ada) was due 24 Nov."], options: [{ label: "Move Server to 28 Nov" }, { label: "Bruno takes Server" }] },
  };
  const onAnswer = vi.fn().mockResolvedValue({ type: "notice", ok: true, text: "ok" });
  render(<ProposalCard proposal={checkin} agentName="Cadence" onAnswer={onAnswer} />);
  expect(screen.getByText("Late: “Server” (Ada) was due 24 Nov.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Bruno takes Server" }));
  expect(onAnswer).toHaveBeenCalledWith({ action: "choose", option: 1 });
});

test("a blocker card is proactive: Mark as blocked, Why?, Helpful, Not now", () => {
  const blocker: Proposal = {
    proposal_id: "e3", kind: "blocker", status: "pending",
    payload: { context: { strategy_id: "cs7_blockers_dependencies", topic: "UI", evidence: [] }, title: "UI", helper_id: 2, question: "What do you need?" },
  };
  render(<ProposalCard proposal={blocker} agentName="Cadence" onAnswer={vi.fn()} memberName={names} />);
  expect(screen.getByText("Bruno")).toBeInTheDocument();
  expect(screen.getAllByRole("button").map((b) => b.textContent?.trim())).toEqual(["Mark as blocked", "Reject", "Why?", "Helpful", "Not now"]);
});

test("the panel lets a member change a task's status and ask why a decision was taken", async () => {
  const onTaskStatus = vi.fn();
  const onWhy = vi.fn().mockResolvedValue("You chose think-aloud.\nSource: “Which test?” → Think-aloud (decided by Bruno on 20 Nov).");
  render(
    <ProjectPanel
      state={{ tasks: [{ task_id: "a", title: "Server", status: "todo", owner_id: 1 }], decisions: [{ question: "Which test?", choice: "Think-aloud" }] }}
      members={[{ id: 1, name: "Ada" }]}
      onKickoff={vi.fn()} onRefresh={vi.fn()} onTaskStatus={onTaskStatus} onWhy={onWhy}
    />,
  );
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Status of Server" }), "done");
  expect(onTaskStatus).toHaveBeenCalledWith("a", "done");
  await userEvent.type(screen.getByLabelText("Ask why the group decided something"), "Why think-aloud?");
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  expect(onWhy).toHaveBeenCalledWith("Why think-aloud?");
  expect(await screen.findByText(/Source: “Which test\?”/)).toBeInTheDocument();
});

test("the calendar link is created on request and can be copied", async () => {
  const onCalendar = vi.fn().mockResolvedValue("http://127.0.0.1:8090/api/calendar/abc.ics");
  render(<ProjectPanel state={{ milestones: [{ title: "Demo", due_date: "2026-12-02" }] }} members={[]} onKickoff={vi.fn()} onRefresh={vi.fn()} onCalendar={onCalendar} />);
  await userEvent.click(screen.getByRole("button", { name: "Add to my calendar" }));
  expect(await screen.findByDisplayValue("http://127.0.0.1:8090/api/calendar/abc.ics")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Make a new link" })).toBeInTheDocument();
});
