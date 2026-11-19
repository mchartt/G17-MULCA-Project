import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useRef, useState } from "react";
import { ProposalCard } from "../console/ProposalCard";
import { faArrowRight, faCheck, faCodeBranch, faCompass, faHandPointer, faScaleBalanced, faUserPen } from "../lib/icons";
import type { Answer, Proposal } from "../lib/types";
import { Nav } from "./Nav";

// The example that runs through the page: two messages of a group chat, then
// the card Cadence posts (CS5, a task with no owner). Same component as in a real space.
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
const memberName = (id: number | string) => EXAMPLE.names?.[String(id)] ?? `member ${id}`;

// How it works, as input → what Cadence notices → result. Each step drives the stage beside it.
const STORY = [
  {
    kicker: "1 · What you give",
    title: "You talk. Cadence listens.",
    text: "Your group chats as usual, in the browser or in Slack and Discord. At the start you share the brief.",
    points: ["Your messages, as you write them", "The assignment and your notes", "Who knows what: name, background, skills"],
  },
  {
    kicker: "2 · What Cadence notices",
    title: "It notices what slips.",
    text: "Cadence steps in only when there is a coordination gap. Otherwise it stays quiet.",
    points: ["A task nobody took", "Work waiting on other work", "A decision going in circles, or reopened"],
  },
  {
    kicker: "3 · What you get",
    title: "You decide. Cadence remembers.",
    text: "One short card with the reason and the messages behind it. One click from any member, and the plan is updated.",
    points: ["Confirm, change, or “not now”", "Tasks, dates and dependencies in one place", "Every decision kept with its why"],
  },
];

// The three needs the tutor named on 18/11, in the group's words.
const NEEDS = [
  { icon: faUserPen, title: "Who does what", text: "A task nobody took gets an owner and a date suggested, with the reason." },
  { icon: faCodeBranch, title: "What waits on what", text: "When one piece of work waits on another, the group sees it before the deadline, and how to unblock it." },
  { icon: faScaleBalanced, title: "What was decided", text: "A choice going in circles gets closed. A decision someone reopens shows what was agreed and why." },
];

// The user guide, in the order the app walks you through it.
const GUIDE = [
  { title: "Create your account", text: "A name, an email, a password." },
  { title: "Tell Cadence who you are", text: "Your background and skills, so it can suggest who could take a task." },
  { title: "Describe the project", text: "Its name, what it is about, and the brief. Drop the documents in." },
  { title: "Invite your team and talk", text: "Share the room code. A short tour shows you the rest." },
];

const RULES = ["Nothing changes until a member confirms.", "It never scores or ranks people.", "It stays quiet when the group is doing fine."];

/** Reduced motion: no scroll effects, everything shown at once. */
const calm = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Adds "is-in" to every [data-reveal] element as it scrolls into view. */
function useReveal(root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const els = root.current?.querySelectorAll<HTMLElement>("[data-reveal]") ?? [];
    if (calm() || typeof IntersectionObserver !== "function") {
      els.forEach((el) => el.classList.add("is-in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && (e.target.classList.add("is-in"), io.unobserve(e.target))),
      { rootMargin: "0px 0px -12% 0px" },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [root]);
}

/** Scroll progress of the page (0..1) as a CSS variable, for the top bar and the hero's tilt. */
function useScrollProgress(root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (calm()) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const max = document.documentElement.scrollHeight - innerHeight;
      root.current?.style.setProperty("--progress", String(max > 0 ? scrollY / max : 0));
      root.current?.style.setProperty("--hero", String(Math.min(1, scrollY / (innerHeight * 0.9))));
    };
    const onScroll = () => (frame ||= requestAnimationFrame(update));
    update();
    addEventListener("scroll", onScroll, { passive: true });
    return () => {
      removeEventListener("scroll", onScroll);
      cancelAnimationFrame(frame);
    };
  }, [root]);
}

/** The step of the story in the middle of the screen. */
function useActiveStep(count: number) {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLElement | null)[]>([]);
  useEffect(() => {
    if (typeof IntersectionObserver !== "function") return;
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setActive(Number((e.target as HTMLElement).dataset.step))),
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.slice(0, count).forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, [count]);
  return { active, refs };
}

/** The picture beside the story: the same little chat, at the step being read. */
function Stage({ step }: { step: number }) {
  return (
    <div className="stage" data-step={step} aria-hidden="true">
      <div className="stage__window">
        <div className="stage__bar"><i /><i /><i /><span>AUI group 17 · Group chat</span></div>
        <div className="stage__body">
          {CHAT.map((m, i) => (
            <div key={m.who} className="stage__msg" style={{ ["--d" as string]: `${i * 120}ms` }}>
              <span className="avatar avatar--small" style={{ background: m.color }}>{m.who[0]}</span>
              <span><strong>{m.who}</strong> {m.text}</span>
            </div>
          ))}
          <div className="stage__card">
            <p className="stage__from"><span className="avatar avatar--agent avatar--small"><FontAwesomeIcon icon={faCompass} /></span> Cadence <em>Ownership</em></p>
            <p className="stage__title">Write the user test plan</p>
            <p className="stage__why">Nobody took this task yet. Sara could own it, by Fri 27 Nov.</p>
            <div className="stage__buttons"><b>Confirm</b><span>Change</span><span>Not now</span></div>
          </div>
          <div className="stage__done">
            <FontAwesomeIcon icon={faCheck} /> Sara confirmed. Added to Tasks: <strong>Write the user test plan</strong> · Sara · 27 Nov
          </div>
        </div>
      </div>
    </div>
  );
}

/** The public page: what Cadence does, how it works step by step, how to start. Every link leads to /login. */
export function Landing() {
  const page = useRef<HTMLDivElement>(null);
  useReveal(page);
  useScrollProgress(page);
  const { active, refs } = useActiveStep(STORY.length);

  return (
    <div className="landing" id="top" ref={page}>
      <div className="progress" aria-hidden="true" />
      <Nav />

      <section className="hero" aria-labelledby="hero-title">
        <div className="hero__glow" aria-hidden="true" />
        <div className="hero__text">
          <p className="hero__kicker">The group coordinator for student projects</p>
          <h1 id="hero-title">Your group talks.<br />Cadence keeps it moving.</h1>
          <p className="hero__lead">
            Cadence reads your group chat, notices when something needs coordinating, and suggests a next step. Your group decides.
          </p>
          <div className="hero__actions">
            <a className="btn btn--primary btn--large" href="/login">Get started <FontAwesomeIcon icon={faArrowRight} /></a>
            <a className="btn btn--ghost btn--large" href="#how">See how it works</a>
          </div>
        </div>

        <figure className="hero__demo" aria-label="Example: two messages, then Cadence's card">
          {/* The buttons answer with a notice: it is an example, not a space. */}
          <figcaption><span className="tag tag--sample">Live example</span> Try the buttons: nothing is saved.</figcaption>
          <ul className="hero__chat">
            {CHAT.map((m) => (
              <li key={m.who}>
                <span className="avatar avatar--small" style={{ background: m.color }} aria-hidden="true">{m.who[0]}</span>
                <span><strong>{m.who}</strong> {m.text}</span>
              </li>
            ))}
          </ul>
          <ProposalCard proposal={EXAMPLE} agentName="Cadence" onAnswer={exampleAnswer} memberName={memberName} />
        </figure>
      </section>

      <section id="how" className="flow" aria-labelledby="how-title">
        <header className="flow__head" data-reveal>
          <p className="eyebrow">How it works</p>
          <h2 id="how-title">From a message to a decision, in three steps.</h2>
        </header>
        <div className="flow__grid">
          <ol className="flow__steps">
            {STORY.map((s, i) => (
              <li key={s.title} ref={(el) => { refs.current[i] = el; }} data-step={i} className={`flow__step${active === i ? " is-active" : ""}`}>
                <p className="flow__kicker">{s.kicker}</p>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
                <ul className="bullets">{s.points.map((p) => <li key={p}>{p}</li>)}</ul>
              </li>
            ))}
          </ol>
          <div className="flow__stage"><Stage step={active} /></div>
        </div>
      </section>

      <section className="needs" aria-labelledby="needs-title">
        <p className="eyebrow" data-reveal>What Cadence notices</p>
        <h2 id="needs-title" data-reveal>Three things that slow every group down.</h2>
        <ul>
          {NEEDS.map((n, i) => (
            <li key={n.title} data-reveal style={{ ["--d" as string]: `${i * 90}ms` }}>
              <span className="needs__icon"><FontAwesomeIcon icon={n.icon} /></span>
              <h3>{n.title}</h3>
              <p>{n.text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="guide" aria-labelledby="guide-title">
        <p className="eyebrow" data-reveal>Getting started</p>
        <h2 id="guide-title" data-reveal>Set up in two minutes. Then just talk.</h2>
        <ol>
          {GUIDE.map((g, i) => (
            <li key={g.title} data-reveal style={{ ["--d" as string]: `${i * 80}ms` }}>
              <span className="guide__n" aria-hidden="true">{i + 1}</span>
              <h3>{g.title}</h3>
              <p>{g.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="rule" aria-labelledby="rule-title">
        <div className="rule__inner" data-reveal>
          <span className="rule__mark" aria-hidden="true"><FontAwesomeIcon icon={faHandPointer} /></span>
          <h2 id="rule-title">Cadence proposes.<br />Your group decides.</h2>
          <ul className="rule__list">{RULES.map((r) => <li key={r}><FontAwesomeIcon icon={faCheck} /> {r}</li>)}</ul>
          <a className="btn btn--primary btn--large" href="/login">Log in or create an account <FontAwesomeIcon icon={faArrowRight} /></a>
        </div>
      </section>

      <footer className="foot">
        <p>Cadence is the Group Coordinator prototype of group 17, Advanced User Interfaces 2026–27, Politecnico di Milano.</p>
        <p><a href="/preview/connections">Previews of what comes next</a>, with sample data. Icons by Font Awesome Free (CC BY 4.0).</p>
      </footer>
    </div>
  );
}
