import { render, screen } from "@testing-library/react";
import type { Proposal } from "../lib/types";
import { cardLang } from "../lib/lang";
import { ProposalCard } from "./ProposalCard";

// Live test 20/11: an Italian group got cards titled "Check-in" with "What is
// late or at risk", "Reject" and "Why?". The card now speaks the language
// Cadence wrote it in, or the one the group chose.

const update: Proposal = {
  proposal_id: "u1",
  kind: "checkin",
  status: "pending",
  rationale: "Richiesta di Gabriele in chat.",
  payload: {
    findings: ["Gabriele: segna Interface designs al 50%"],
    options: [{ label: "«Interface designs»: avanzamento 50%" }],
    requested: true,
  },
};

const owner: Proposal = {
  proposal_id: "o1",
  kind: "task_owner",
  status: "pending",
  rationale: "Stepping in because this task has no owner yet.",
  payload: {
    context: { strategy_id: "cs5_owner_and_date", topic: "slides", evidence: [] },
    title: "Slides",
    owner_id: null,
    due_date: null,
  },
};

const names = (id: unknown) => (id === 2 ? "Sara" : "a member");

test("an update asked in Italian is titled as an update, in Italian", () => {
  render(<ProposalCard proposal={update} agentName="Cadence" onAnswer={vi.fn()} memberName={names} />);
  expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Aggiornare un'attività");
  expect(screen.getByText("Cosa è stato chiesto")).toBeInTheDocument();
  expect(screen.queryByText("What is late or at risk")).toBeNull();
  expect(screen.getByRole("button", { name: /Rifiuta/ })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("In attesa che un membro confermi");
});

test("an English card stays English, and a chosen language wins", () => {
  const { rerender } = render(<ProposalCard proposal={owner} agentName="Cadence" onAnswer={vi.fn()} memberName={names} />);
  expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Owner and date");
  expect(screen.getByRole("button", { name: /I'll take it/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Why\?/ })).toBeInTheDocument();
  rerender(<ProposalCard proposal={owner} agentName="Cadence" onAnswer={vi.fn()} memberName={names} language="it" />);
  expect(screen.getByRole("heading", { level: 3 })).toHaveTextContent("Responsabile e data");
  expect(screen.getByRole("button", { name: /Me ne occupo io/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Perché\?/ })).toBeInTheDocument();
});

test("the card's language comes from what Cadence wrote on it", () => {
  expect(cardLang(update)).toBe("it");
  expect(cardLang(owner)).toBe("en");
  expect(cardLang(update, "en")).toBe("en");
});
