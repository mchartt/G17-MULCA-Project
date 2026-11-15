import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Proposal } from "../lib/types";
import { ProposalCard } from "./ProposalCard";

const context = {
  strategy_id: "cs2_delegate_simple_task",
  topic: "Fonts and margins",
  evidence: [{ speaker: "Ada", text: "Arial or Helvetica?", at_ms: 1 }],
};
const delegation: Proposal = {
  proposal_id: "d1",
  kind: "delegation",
  status: "pending",
  rationale: "Stepping in because one person can do this.",
  payload: { context, title: "Fix the fonts", due_date: null, return_to: "Evaluation protocol" },
};
const task: Proposal = { ...delegation, proposal_id: "t1", kind: "task_owner", payload: { ...delegation.payload, owner_id: 2, due_date: "2026-11-27" } };
const decision: Proposal = {
  ...delegation,
  proposal_id: "c1",
  kind: "decision",
  payload: {
    context: { ...context, strategy_id: "cs3_close_decision", topic: "Test method" },
    question: "Which usability test?",
    options: [{ label: "Think-aloud", argument: "Shows why users get stuck." }, { label: "SUS", argument: "Fast." }],
  },
};
const names = (id: number) => ({ 2: "Bruno" })[id] ?? "?";

test("a delegation card never names an owner: I'll take it, Reject, Why?, Helpful, Not now", () => {
  render(<ProposalCard proposal={delegation} agentName="Cadence" onAnswer={vi.fn()} memberName={names} />);
  expect(screen.getByRole("heading", { name: "One person can do this" })).toBeInTheDocument();
  expect(screen.getByText("Fix the fonts")).toBeInTheDocument();
  expect(screen.getByText("Evaluation protocol")).toBeInTheDocument();
  expect(screen.queryByText("Suggested owner")).toBeNull();
  const buttons = screen.getAllByRole("button").map((b) => b.textContent?.trim());
  expect(buttons).toEqual(["I'll take it", "Reject", "Why?", "Helpful", "Not now"]);
});

test("a task card shows the suggested owner by name and can be confirmed or taken", async () => {
  const onAnswer = vi.fn().mockResolvedValue({ type: "notice", ok: true, text: "Saved." });
  render(<ProposalCard proposal={task} agentName="Cadence" onAnswer={onAnswer} memberName={names} />);
  expect(screen.getByText("Bruno")).toBeInTheDocument();
  expect(screen.getByText("27 Nov")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "I'll take it" }));
  expect(onAnswer).toHaveBeenCalledWith({ action: "take" });
  await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
  expect(onAnswer).toHaveBeenLastCalledWith({ action: "confirm" });
});

test("a decision card has one button per option, which sends its index", async () => {
  const onAnswer = vi.fn().mockResolvedValue({ type: "notice", ok: true, text: "Decision saved: SUS." });
  render(<ProposalCard proposal={decision} agentName="Cadence" onAnswer={onAnswer} />);
  expect(screen.getByText("Shows why users get stuck.", { exact: false })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "SUS" }));
  expect(onAnswer).toHaveBeenCalledWith({ action: "choose", option: 1 });
});

test("Why? opens the strategy, the topic and the messages behind the card, from the keyboard too", async () => {
  render(<ProposalCard proposal={delegation} agentName="Cadence" onAnswer={vi.fn()} />);
  const why = screen.getByRole("button", { name: "Why?" });
  expect(why).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("Arial or Helvetica?")).not.toBeVisible();
  why.focus();
  await userEvent.keyboard("{Enter}");
  expect(why).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("Arial or Helvetica?")).toBeVisible();
  expect(screen.getByText("Topic: Fonts and margins")).toBeInTheDocument();
  expect(screen.getByText(/one person can do alone/)).toBeInTheDocument();
});

test("Not now sends not_now; a snoozed card says so and keeps only Why?", async () => {
  const onAnswer = vi.fn().mockResolvedValue({ type: "notice", ok: true, text: "Got it." });
  const { rerender } = render(<ProposalCard proposal={delegation} agentName="Cadence" onAnswer={onAnswer} />);
  await userEvent.click(screen.getByRole("button", { name: "Not now" }));
  expect(onAnswer).toHaveBeenCalledWith({ action: "not_now" });
  rerender(<ProposalCard proposal={{ ...delegation, status: "snoozed" }} agentName="Cadence" onAnswer={onAnswer} />);
  expect(screen.getByRole("status")).toHaveTextContent("Not now: silenced on this topic for 30 minutes");
  expect(screen.getAllByRole("button").map((b) => b.textContent?.trim())).toEqual(["Why?"]);
});

test("a charter card has no Why? or Not now (the group asked for it)", () => {
  const charter: Proposal = { proposal_id: "p1", kind: "charter", status: "pending", payload: { goal: "Ship it." } };
  render(<ProposalCard proposal={charter} agentName="Cadence" onAnswer={vi.fn()} />);
  expect(screen.queryByRole("button", { name: "Why?" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Not now" })).toBeNull();
});

test("Helpful sends feedback, thanks the member and changes nothing on the card", async () => {
  const onAnswer = vi.fn().mockResolvedValue({ type: "notice", ok: true, text: "Thanks: noted as helpful (1 member so far)." });
  render(<ProposalCard proposal={delegation} agentName="Cadence" onAnswer={onAnswer} />);
  await userEvent.click(screen.getByRole("button", { name: "Helpful" }));
  expect(onAnswer).toHaveBeenCalledWith({ action: "helpful" });
  expect(await screen.findByText("Thanks: noted as helpful (1 member so far).")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Marked helpful" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "I'll take it" })).toBeEnabled();
});

test("a card asked for by a member has no Helpful button", () => {
  const charter: Proposal = { proposal_id: "k1", kind: "charter", status: "pending", payload: { goal: "Ship", deliverables: [], milestones: [] } };
  render(<ProposalCard proposal={charter} agentName="Cadence" onAnswer={vi.fn()} />);
  expect(screen.queryByRole("button", { name: "Helpful" })).toBeNull();
});
