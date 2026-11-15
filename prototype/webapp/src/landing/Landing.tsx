import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useCallback, useState } from "react";
import { ProposalCard } from "../console/ProposalCard";
import { faCalendarCheck, faFileLines, faHandPointer, faUsers } from "../lib/icons";
import { useReveal, useScrollProgress, useSmoothScroll } from "../lib/motion";
import type { Answer, Proposal } from "../lib/types";
import { Entry } from "./Entry";
import { FilmHero } from "./FilmHero";
import { Nav } from "./Nav";

const STEPS = [
  { icon: faFileLines, title: "Paste the assignment", text: "Cadence lists what you have to deliver and by when, asks at most two questions and proposes the group's goal." },
  { icon: faUsers, title: "Split the work", text: "Each member writes what needs doing; Cadence suggests an owner for each task, with the reason." },
  { icon: faHandPointer, title: "Keep talking as usual", text: "When an action has no owner or a decision drags on, a short card appears in the chat with one clear request." },
  { icon: faCalendarCheck, title: "Check in before deadlines", text: "Owners say where they are; Cadence compares it with the plan and offers up to three ways forward." },
];

// An example of the one kind of card that exists today (project charter).
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

const PROBLEM = "Splitting the work only helps if coordinating it costs less than it saves.";

/** Words go from grey to ink as the headline scrolls through the screen. */
function LitHeadline({ text }: { text: string }) {
  const [p, setP] = useState(0);
  const onProgress = useCallback((v: number) => setP(v), []);
  const ref = useScrollProgress<HTMLHeadingElement>(onProgress);
  const words = text.split(" ");
  return (
    <h2 ref={ref} id="problem-title" className="lit" aria-label={text}>
      {words.map((w, i) => (
        <span key={i} aria-hidden="true" className={p * (words.length + 3) > i + 2 ? "lit__on" : undefined}>
          {w}{" "}
        </span>
      ))}
    </h2>
  );
}

export function Landing({ onEnter }: { onEnter: (token: string) => void }) {
  useSmoothScroll(true);
  const steps = useReveal<HTMLOListElement>();
  const rule = useReveal<HTMLDivElement>();
  return (
    <div className="landing" id="top">
      <Nav />
      <FilmHero />

      <section className="problem" aria-labelledby="problem-title">
        <LitHeadline text={PROBLEM} />
        <p>
          In a group of peers nobody is in charge of the process, so it gets skipped or quietly lands on one person.
          Cadence takes that job: it keeps the goal, the plan and the decisions in one place and steps into the chat only when the group needs it.
        </p>
      </section>

      <section id="how" className="steps" aria-labelledby="how-title">
        <h2 id="how-title">How a project runs with Cadence.</h2>
        <ol ref={steps} className="bento reveal">
          {STEPS.map((s, i) => (
            <li key={s.title} style={{ transitionDelay: `${i * 90}ms` }}>
              <span className="bento__icon"><FontAwesomeIcon icon={s.icon} /></span>
              <p className="bento__step">Step {i + 1}</p>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="rule" aria-labelledby="rule-title">
        <h2 id="rule-title">Nothing changes until someone clicks.</h2>
        <p className="rule__lead">Cadence never edits your plan on its own. Every proposal says why it appears, asks for one thing, and waits. The first member to confirm applies it for everyone.</p>
        <div ref={rule} className="rule__card reveal">
          <ProposalCard proposal={EXAMPLE} agentName="Cadence" onAnswer={exampleAnswer} />
        </div>
      </section>

      <Entry onEnter={onEnter} />

      <footer className="foot">
        <p>Cadence is the Group Coordinator prototype of group 17, Advanced User Interfaces 2026–27, Politecnico di Milano.</p>
        <p>Icons by Font Awesome Free (CC BY 4.0).</p>
      </footer>
    </div>
  );
}
