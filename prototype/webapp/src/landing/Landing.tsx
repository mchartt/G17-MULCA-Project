import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { ProposalCard } from "../console/ProposalCard";
import { faArrowRight, faCodeBranch, faFileLines, faHandPointer, faScaleBalanced, faUserPen, faUsers } from "../lib/icons";
import type { Answer, Proposal } from "../lib/types";
import { Nav } from "./Nav";

// The example in the hero: two messages of a group chat, then the card Cadence
// posts (CS5, a task with no owner). Same component as in a real space.
const CHAT = [
  { who: "Marco", color: "var(--m1)", text: "Someone has to write the user test plan before Thursday." },
  { who: "Sara", color: "var(--m2)", text: "Yes, we can't run the tests without it." },
];
const EXAMPLE: Proposal = {
  proposal_id: "example",
  kind: "task_owner",
  status: "pending",
  rationale: "Stepping in because this task has no owner yet.",
  names: { 2: "Sara" },
  payload: {
    title: "Write the user test plan",
    owner_id: 2,
    due_date: "2026-11-27",
    context: {
      strategy_id: "cs5_owner_and_date",
      topic: "User test plan",
      evidence: CHAT.map((m, i) => ({ speaker: m.who, text: m.text, at_ms: i })),
    },
  },
};
const exampleAnswer = async (): Promise<Answer> => ({ type: "notice", ok: false, text: "This is an example card. Open a space to try a real one." });

// The three needs the tutor named on 18/11, in the group's words.
const NEEDS = [
  { icon: faUserPen, title: "Who does what", text: "A task nobody took gets an owner and a date suggested, with the reason." },
  { icon: faCodeBranch, title: "What waits on what", text: "When one piece of work is stuck waiting on another, the group sees it before the deadline." },
  { icon: faScaleBalanced, title: "What was decided", text: "A choice going in circles gets closed, and a decision someone reopens shows what was agreed and why." },
];

const STEPS = [
  { icon: faUsers, title: "Create a space and send the link", text: "Your group joins with one click." },
  { icon: faFileLines, title: "Paste the brief", text: "Cadence proposes the goal, deliverables and milestones. You confirm them." },
  { icon: faHandPointer, title: "Talk as usual", text: "Cadence stays quiet until something needs coordinating." },
];

/** The public page, short: what Cadence does, one example, three steps, and the way in (/login). */
export function Landing() {
  return (
    <div className="landing" id="top">
      <Nav />

      <section className="hero" aria-labelledby="hero-title">
        <div className="hero__text">
          <p className="hero__kicker">Cadence, for student group projects</p>
          <h1 id="hero-title">Your group talks. Cadence keeps track.</h1>
          <p className="hero__lead">
            Cadence reads your group chat and steps in only when something needs coordinating, with one short card.
            Nothing changes until one of you confirms.
          </p>
          <div className="hero__actions">
            <a className="btn btn--primary" href="/login">Create a space <FontAwesomeIcon icon={faArrowRight} /></a>
            <a className="btn btn--soft" href="/login">Join with an invite</a>
          </div>
          <p className="muted small">In the browser, and in Discord or Slack where the Cadence bot is installed.</p>
        </div>

        <figure className="hero__demo" aria-label="Example: two messages, then Cadence's card">
          <ul className="hero__chat">
            {CHAT.map((m) => (
              <li key={m.who}>
                <span className="avatar avatar--small" style={{ background: m.color }} aria-hidden="true">{m.who[0]}</span>
                <span><strong>{m.who}</strong> {m.text}</span>
              </li>
            ))}
          </ul>
          <ProposalCard proposal={EXAMPLE} agentName="Cadence" onAnswer={exampleAnswer} memberName={(id) => EXAMPLE.names?.[String(id)] ?? `member ${id}`} />
        </figure>
      </section>

      <section className="needs" aria-labelledby="needs-title">
        <h2 id="needs-title">What Cadence notices.</h2>
        <ul>
          {NEEDS.map((n) => (
            <li key={n.title}>
              <span className="needs__icon"><FontAwesomeIcon icon={n.icon} /></span>
              <h3>{n.title}</h3>
              <p>{n.text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section id="how" className="how" aria-labelledby="how-title">
        <h2 id="how-title">Three steps, then just talk.</h2>
        <ol>
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <span className="how__n" aria-hidden="true">{i + 1}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
        <a className="btn btn--primary" href="/login">Log in or create an account <FontAwesomeIcon icon={faArrowRight} /></a>
      </section>

      <footer className="foot">
        <p>Cadence is the Group Coordinator prototype of group 17, Advanced User Interfaces 2026–27, Politecnico di Milano.</p>
        <p><a href="/preview/connections">Previews of what comes next</a>, with sample data. Icons by Font Awesome Free (CC BY 4.0).</p>
      </footer>
    </div>
  );
}
