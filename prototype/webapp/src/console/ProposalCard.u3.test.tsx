import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Proposal } from "../lib/types";
import { ProposalCard } from "./ProposalCard";

// U3: the card says what kind of help it is, how sure Cadence is, and who answered.
const evidence = [{ speaker: "Sara", text: "booked five testers for Friday", at_ms: 1 }];
const possible: Proposal = {
  proposal_id: "b1",
  kind: "blocker",
  status: "pending",
  rationale: "Stepping in because Friday's test may need the booking API, due Saturday.",
  payload: {
    context: { strategy_id: "cs7_blockers_dependencies", topic: "Test waits on API", evidence },
    certainty: "possible",
    title: "Usability test",
    depends_on_title: "Booking API",
    helper_id: 3,
    question: "Is the API needed for Friday's test, or could Sara use mock data?",
    ways_forward: ["Test with mock data", "Marco ships a minimal booking flow first"],
  },
};
const revisit: Proposal = {
  proposal_id: "r1",
  kind: "revisit",
  status: "pending",
  rationale: "Stepping in because tabs were chosen on purpose.",
  payload: {
    context: { strategy_id: "cs3_reopened_decision", topic: "Navigation", evidence },
    question: "App navigation",
    choice: "Tabs",
    reason: "Five sections fit; testers missed the side menu",
    new_point: "",
    options: [{ label: "Keep “Tabs”" }, { label: "Reopen it" }],
  },
};
const names = (id: number | string) => ({ 2: "Sara", 3: "Marco" })[id] ?? "?";

test("a possible dependency says it is not confirmed, what it may wait on and the ways forward", () => {
  render(<ProposalCard proposal={possible} agentName="Cadence" onAnswer={vi.fn()} memberName={names} />);
  expect(screen.getByRole("heading", { name: "Possible dependency" })).toBeInTheDocument();
  expect(screen.getByText("Dependency")).toBeInTheDocument();
  expect(screen.getByText("Not confirmed yet")).toBeInTheDocument();
  expect(screen.getByText("May wait on")).toBeInTheDocument();
  expect(screen.getByText("Booking API")).toBeInTheDocument();
  expect(screen.getByText("Marco")).toBeInTheDocument();
  expect(screen.getByText("Test with mock data")).toBeInTheDocument();
  const buttons = screen.getAllByRole("button").map((b) => b.textContent?.trim());
  expect(buttons).toEqual(["Yes, it depends", "No, it doesn't", "Why?", "Helpful", "Not now"]);
});

test("confirming a possible dependency sends confirm, saying no sends reject", async () => {
  const onAnswer = vi.fn().mockResolvedValue({ type: "notice", ok: true, text: "Dependency saved." });
  render(<ProposalCard proposal={possible} agentName="Cadence" onAnswer={onAnswer} memberName={names} />);
  await userEvent.click(screen.getByRole("button", { name: "Yes, it depends" }));
  expect(onAnswer).toHaveBeenCalledWith({ action: "confirm" });
  await userEvent.click(screen.getByRole("button", { name: "No, it doesn't" }));
  expect(onAnswer).toHaveBeenLastCalledWith({ action: "reject" });
});

test("a stated blocker keeps Mark as blocked and has no 'not confirmed' tag", () => {
  const stated: Proposal = { ...possible, payload: { ...possible.payload, certainty: "blocked" } };
  render(<ProposalCard proposal={stated} agentName="Cadence" onAnswer={vi.fn()} memberName={names} />);
  expect(screen.getByRole("heading", { name: "Something is blocked" })).toBeInTheDocument();
  expect(screen.queryByText("Not confirmed yet")).toBeNull();
  expect(screen.getByText("Waits on")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Mark as blocked" })).toBeInTheDocument();
});

test("a reopened decision recalls the choice and its reason; Keep and Reopen send their option", async () => {
  const onAnswer = vi.fn().mockResolvedValue({ type: "notice", ok: true, text: "Kept." });
  render(<ProposalCard proposal={revisit} agentName="Cadence" onAnswer={onAnswer} memberName={names} />);
  expect(screen.getByRole("heading", { name: "Already decided" })).toBeInTheDocument();
  expect(screen.getByText("Tabs")).toBeInTheDocument();
  expect(screen.getByText("Five sections fit; testers missed the side menu")).toBeInTheDocument();
  expect(screen.getByText("Nothing new so far: the same arguments as before.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Keep “Tabs”" }));
  expect(onAnswer).toHaveBeenCalledWith({ action: "choose", option: 0 });
  await userEvent.click(screen.getByRole("button", { name: "Reopen it" }));
  expect(onAnswer).toHaveBeenLastCalledWith({ action: "choose", option: 1 });
});

test("once answered, the card says who answered it", () => {
  const done: Proposal = { ...possible, status: "applied", resolved_by: 2 };
  const { rerender } = render(<ProposalCard proposal={done} agentName="Cadence" onAnswer={vi.fn()} memberName={names} />);
  expect(screen.getByRole("status")).toHaveTextContent("Confirmed by Sara");
  rerender(<ProposalCard proposal={{ ...done, status: "rejected" }} agentName="Cadence" onAnswer={vi.fn()} memberName={names} />);
  expect(screen.getByRole("status")).toHaveTextContent("Turned down by Sara");
  rerender(<ProposalCard proposal={{ ...done, status: "applied", resolved_by: null }} agentName="Cadence" onAnswer={vi.fn()} memberName={names} />);
  expect(screen.getByRole("status")).toHaveTextContent("Confirmed");
});

test("a dependency on new work names who delivers it, when the chat said so", () => {
  const rasd: Proposal = {
    ...possible,
    payload: { ...possible.payload, title: "Rivedere il RASD", depends_on_title: "Dati del RASD", depends_on_owner_id: 2, helper_id: null },
  };
  render(<ProposalCard proposal={rasd} agentName="Cadence" onAnswer={vi.fn()} memberName={names} />);
  expect(screen.getByText("Delivered by").parentElement).toHaveTextContent("Delivered bySara");
});
