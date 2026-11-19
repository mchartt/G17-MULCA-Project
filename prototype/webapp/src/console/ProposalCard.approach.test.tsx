// The plan opener's card (CS-OPEN-01): what the group said about how it plans the work.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Proposal } from "../lib/types";
import { ProposalCard } from "./ProposalCard";

const approach: Proposal = {
  proposal_id: "a1",
  kind: "approach",
  status: "pending",
  rationale: "Stepping in because you said how you want to work.",
  payload: {
    context: {
      strategy_id: "plan_opener",
      topic: "how you plan the work",
      evidence: [{ speaker: "Ada", text: "Let's split by area.", at_ms: 1 }],
    },
    question: "How the group plans the work",
    summary: "Split by area, check in every Monday after the lab.",
    agreements: ["Split by area", "Check in every Monday after the lab"],
    open_points: ["Where to keep the slides"],
  },
};

test("the approach card shows the summary, what was agreed and what is still open", () => {
  render(<ProposalCard proposal={approach} agentName="Cadence" onAnswer={vi.fn()} />);
  const card = screen.getByRole("article", { name: "How you plan the work" });
  expect(within(card).getByText("Split by area, check in every Monday after the lab.")).toBeInTheDocument();
  expect(within(card).getByText("Check in every Monday after the lab")).toBeInTheDocument();
  expect(within(card).getByText("Where to keep the slides")).toBeInTheDocument();
  expect(within(card).getByText("Plan")).toHaveClass("card__need");
});

test("Confirm, Reject and Not now; Why? shows the answers it rests on", async () => {
  const onAnswer = vi.fn(async () => ({ type: "notice" as const, ok: true, text: "Saved." }));
  render(<ProposalCard proposal={approach} agentName="Cadence" onAnswer={onAnswer} />);
  await userEvent.click(screen.getByRole("button", { name: /Why\?/ }));
  expect(screen.getByText("Let's split by area.")).toBeVisible();
  expect(screen.getByText(/Cadence asked how you want to plan the work/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Confirm/ }));
  expect(onAnswer).toHaveBeenCalledWith({ action: "confirm" });
  expect(screen.getByRole("button", { name: /Reject/ })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Not now/ }));
  expect(onAnswer).toHaveBeenCalledWith({ action: "not_now" });
});
