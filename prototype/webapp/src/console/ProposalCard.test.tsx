import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Proposal } from "../lib/types";
import { ProposalCard } from "./ProposalCard";

const pending: Proposal = {
  proposal_id: "p1",
  kind: "charter",
  status: "pending",
  rationale: "Stepping in because you pasted the assignment.",
  payload: { goal: "Ship the coordinator.", deliverables: ["Report"], milestones: [{ title: "Demo", due_date: "2026-12-02" }, { title: "Pitch" }] },
};

test("a pending card shows who, why, the content, the status in words and two buttons", () => {
  render(<ProposalCard proposal={pending} agentName="Cadence" onAnswer={vi.fn()} />);
  expect(screen.getByRole("heading", { name: "Project charter" })).toBeInTheDocument();
  expect(screen.getByText("Cadence")).toBeInTheDocument();
  expect(screen.getByText(pending.rationale!)).toBeInTheDocument();
  expect(screen.getByText("Ship the coordinator.")).toBeInTheDocument();
  expect(screen.getByText("2 Dec")).toBeInTheDocument();
  expect(screen.getByText("no date yet")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Waiting for a member to confirm");
  expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
});

test.each([
  ["applied", "Confirmed"],
  ["rejected", "Rejected"],
  ["expired", "Expired: nothing was changed"],
] as const)("a %s card says so in words and has no buttons", (status, words) => {
  render(<ProposalCard proposal={{ ...pending, status }} agentName="Cadence" onAnswer={vi.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent(words);
  expect(screen.queryByRole("button")).toBeNull();
});

test("clicking Confirm sends the action once and shows a refusal from the server", async () => {
  const onAnswer = vi.fn().mockResolvedValue({ type: "notice", ok: false, text: "Only members of this group can use the coordinator here." });
  render(<ProposalCard proposal={pending} agentName="Cadence" onAnswer={onAnswer} />);
  await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
  expect(onAnswer).toHaveBeenCalledTimes(1);
  expect(onAnswer).toHaveBeenCalledWith("confirm");
  expect(await screen.findByRole("alert")).toHaveTextContent("Only members of this group");
});

test("buttons are disabled while the click is on its way", async () => {
  let resolve!: (v: unknown) => void;
  const onAnswer = vi.fn(() => new Promise((r) => (resolve = r)));
  render(<ProposalCard proposal={pending} agentName="Cadence" onAnswer={onAnswer as never} />);
  await userEvent.click(screen.getByRole("button", { name: "Reject" }));
  expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  resolve({ type: "notice", ok: true, text: "Rejected." });
});
