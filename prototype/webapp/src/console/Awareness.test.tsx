// Matteo's 20/11 screenshots: "**30%**" shown with its asterisks on a card, and
// no sign that Cadence was working on an answer.
import { act, render, screen } from "@testing-library/react";
import type { Proposal } from "../lib/types";
import { Thinking, THINKING_DELAY_MS } from "./Chat";
import { ProposalCard } from "./ProposalCard";
import { emptySpace, reduce } from "./space";

const card = {
  proposal_id: "p1",
  kind: "checkin",
  status: "pending",
  rationale: "Ho preparato l'aggiornamento di Frontend Application al **30%**: vuoi confermarlo?",
  payload: { findings: ["Ada: sono al **30%**"], options: [{ label: "«Frontend Application»: avanzamento 30%", task_id: "t1", new_progress: 30 }] },
  expires_at: 9999999999,
} as unknown as Proposal;

test("a card shows Cadence's bold as bold, never the asterisks", () => {
  render(<ProposalCard proposal={card} agentName="Cadence" onAnswer={vi.fn()} />);
  expect(screen.queryByText(/\*\*/)).toBeNull();
  expect(screen.getAllByText("30%").every((el) => el.tagName === "STRONG")).toBe(true);
});

test("the thinking banner waits a moment, so a quick answer never flickers it", () => {
  vi.useFakeTimers();
  render(<Thinking name="Cadence" />);
  expect(screen.queryByRole("status")).toBeNull();
  act(() => { vi.advanceTimersByTime(THINKING_DELAY_MS); });
  expect(screen.getByRole("status").textContent).toContain("Cadence is thinking…");
  vi.useRealTimers();
});

test("thinking follows the server: on, then off", () => {
  const on = reduce(emptySpace, { type: "thinking", on: true });
  expect(on.thinking).toBe(true);
  expect(reduce(on, { type: "thinking", on: false }).thinking).toBe(false);
});
