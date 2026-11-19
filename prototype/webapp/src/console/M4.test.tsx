import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Proposal } from "../lib/types";
import { ProposalCard } from "./ProposalCard";

const names = (id: number | string) => ({ 1: "Ada", 2: "Bruno" })[id] ?? "?";

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
