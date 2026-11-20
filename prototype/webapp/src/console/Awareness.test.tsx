// Matteo's 20/11 screenshots: "**30%**" shown with its asterisks on a card, and
// no sign that Cadence was working on an answer.
import { render, screen } from "@testing-library/react";
import type { Proposal, ServerEvent } from "../lib/types";
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

test("thinking follows the server: on, then off", () => {
  const on = reduce(emptySpace, { type: "typing", on: true });
  expect(on.thinking).toBe(true);
  expect(reduce(on, { type: "typing", on: false }).thinking).toBe(false);
});

test("a reconnect takes the banner from the server, so a missed 'off' never leaves it on", () => {
  const stuck = { ...emptySpace, thinking: true };
  const hello: Extract<ServerEvent, { type: "hello" }> = { type: "hello", agentName: "Cadence", group: { id: 1, name: "T", inviteCode: "x" }, me: { id: 1, name: "Ada" }, members: [], messages: [] };
  expect(reduce(stuck, hello).thinking).toBe(false);
  expect(reduce(emptySpace, { ...hello, thinking: true }).thinking).toBe(true);
});
