import type { Answer, Proposal } from "../lib/types";
import { ProposalCard } from "../console/ProposalCard";
import { Entry } from "./Entry";
import { FilmHero } from "./FilmHero";

const STEPS = [
  { title: "Paste the assignment", text: "Cadence lists what you have to deliver and by when, asks at most two questions and proposes the group's goal." },
  { title: "Split the work", text: "Each member writes what needs doing; Cadence suggests an owner for each task, with the reason." },
  { title: "Keep talking as usual", text: "When an action has no owner or a decision drags on, a short card appears in the chat with one clear request." },
  { title: "Check in before deadlines", text: "Owners say where they are; Cadence compares it with the plan and offers up to three ways forward." },
];

// Shown as an example of a real card, not wired to any group.
const EXAMPLE: Proposal = {
  proposal_id: "example",
  kind: "charter",
  status: "pending",
  rationale: "Stepping in because you pasted the assignment: here is the goal as I read it.",
  payload: {
    goal: "Build and demo a working prototype of our group coordinator.",
    deliverables: ["Report with needs, goals and scenarios", "Prototype and source code", "Two-minute video pitch"],
    milestones: [{ title: "Demo Madness", due_date: "2026-12-02" }],
  },
};
const exampleAnswer = async (): Promise<Answer> => ({ type: "notice", ok: false, text: "This is an example card. Open a space to try a real one." });

export function Landing({ onEnter }: { onEnter: (token: string) => void }) {
  return (
    <div className="landing">
      <FilmHero />

      <section className="problem" aria-labelledby="problem-title">
        <h2 id="problem-title">Splitting the work only helps if coordinating it costs less than it saves.</h2>
        <p>
          In a group of peers nobody is in charge of the process, so it gets skipped or quietly lands on one person.
          Cadence takes that job: it keeps the goal, the plan and the decisions in one place and steps into the chat only when the group needs it.
        </p>
      </section>

      <section id="how" className="steps" aria-labelledby="how-title">
        <h2 id="how-title">How a project runs with Cadence</h2>
        <ol>
          {STEPS.map((s) => (
            <li key={s.title}>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="rule" aria-labelledby="rule-title">
        <div className="rule__text">
          <h2 id="rule-title">Nothing changes until someone clicks.</h2>
          <p>Cadence never edits your plan on its own. Every proposal says why it appears, asks for one thing, and waits. The first member to confirm applies it for everyone, in every channel.</p>
        </div>
        <div className="rule__card">
          <ProposalCard proposal={EXAMPLE} agentName="Cadence" onAnswer={exampleAnswer} />
        </div>
      </section>

      <Entry onEnter={onEnter} />

      <footer className="foot">
        <p>Cadence is the Group Coordinator prototype of group 17, Advanced User Interfaces 2026–27, Politecnico di Milano.</p>
      </footer>
    </div>
  );
}
