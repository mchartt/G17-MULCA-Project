import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type PointerEvent } from "react";
import { Logo, LogoMark } from "../brand/Logo";
import { ProposalCard } from "../console/ProposalCard";
import { saveDraftBrief } from "../lib/brief";
import { faArrowUp, faCheck, faCodeBranch, faScaleBalanced, faUserPen } from "../lib/icons";
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

// How it works, as input → what Cadence notices → result. Each step drives the app window beside it.
const STORY = [
  {
    kicker: "What you give",
    title: "You talk. Cadence listens.",
    text: "Your group chats as usual, in the browser or in Slack and Discord. At the start you share the brief.",
    points: ["Your messages, as you write them", "The assignment and your notes", "Who knows what: name, background, skills"],
  },
  {
    kicker: "What Cadence notices",
    title: "It notices what slips.",
    text: "Cadence steps in only when there is a coordination gap. Otherwise it stays quiet.",
    points: ["A task nobody took", "Work waiting on other work", "A decision going in circles, or reopened"],
  },
  {
    kicker: "What you get",
    title: "You decide. Cadence remembers.",
    text: "One short card with the reason and the messages behind it. One click from any member, and the plan is updated.",
    points: ["Confirm, change, or “not now”", "Tasks, dates and dependencies in one place", "Every decision kept with its why"],
  },
];

const STATEMENT = "Your group talks. Cadence keeps it moving. You decide.".split(" ");

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

// The three cards fanned in the dark band: the three kinds of help.
const FAN = [
  { need: "Ownership", title: "Write the user test plan", line: "Nobody took it yet. Sara could own it, by 27 Nov." },
  { need: "Dependency", title: "Dashboard waits on the API", line: "Mock data could let Sara start testing on Friday." },
  { need: "Decision", title: "Think-aloud or SUS?", line: "Two options, both argued. Close it with one click." },
];

const RULES = ["Nothing changes until a member confirms.", "It never scores or ranks people.", "It stays quiet when the group is doing fine."];

/** Reduced motion: no scroll or pointer effects, everything shown at once. */
const calm = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Scroll progress as CSS variables, one rAF per frame:
 *   on the page   --progress (0..1 of the whole page), --hero (0..1 over the first screen);
 *   on every [data-scroll] element  --p (0 when its top reaches the bottom of the screen,
 *   1 when its bottom leaves the top). CSS does the rest (word fill, line, fan).
 */
function useScrollVars(root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const page = root.current;
    if (!page) return;
    if (calm()) {
      page.querySelectorAll<HTMLElement>("[data-scroll]").forEach((el) => el.style.setProperty("--p", "1"));
      page.style.setProperty("--hero", "0");
      return;
    }
    let frame = 0;
    const update = () => {
      frame = 0;
      const max = document.documentElement.scrollHeight - innerHeight;
      page.style.setProperty("--progress", String(max > 0 ? scrollY / max : 0));
      page.style.setProperty("--hero", String(Math.min(1, scrollY / (innerHeight * 0.9))));
      page.querySelectorAll<HTMLElement>("[data-scroll]").forEach((el) => {
        const r = el.getBoundingClientRect();
        const p = (innerHeight - r.top) / (innerHeight + r.height);
        el.style.setProperty("--p", String(Math.max(0, Math.min(1, p))));
      });
    };
    const onScroll = () => (frame ||= requestAnimationFrame(update));
    update();
    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("resize", onScroll);
    return () => {
      removeEventListener("scroll", onScroll);
      removeEventListener("resize", onScroll);
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
            <p className="stage__from"><LogoMark size={18} /> Cadence <em>Ownership</em></p>
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

/** The hero's prompt bar: what the group is working on goes with the member to the sign-up and pre-fills the project. */
function PromptBar() {
  const [text, setText] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    saveDraftBrief(text);
    location.assign("/login");
  };
  return (
    <form className="prompt" onSubmit={submit}>
      <label htmlFor="hero-prompt" className="sr-only">Describe your group project</label>
      <input
        id="hero-prompt"
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={400}
        placeholder="Describe your group project…"
        autoComplete="off"
      />
      <button type="submit" className="prompt__send" aria-label="Start with this description">
        <FontAwesomeIcon icon={faArrowUp} />
      </button>
    </form>
  );
}

/** The public page: what Cadence does, how it works step by step, how to start. Every way in leads to /login. */
export function Landing() {
  const page = useRef<HTMLDivElement>(null);
  useScrollVars(page);
  const { active, refs } = useActiveStep(STORY.length);

  // A gentle 3D tilt of the hero picture, following the pointer (not with reduced motion).
  const tilt = (e: PointerEvent<HTMLElement>) => {
    if (calm() || e.pointerType !== "mouse") return;
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--tx", String((e.clientX - r.left) / r.width - 0.5));
    e.currentTarget.style.setProperty("--ty", String((e.clientY - r.top) / r.height - 0.5));
  };

  return (
    <div className="landing" id="top" ref={page}>
      <div className="progress" aria-hidden="true" />
      <Nav />

      <section className="hero" aria-labelledby="hero-title" onPointerMove={tilt}>
        <div className="hero__glow" aria-hidden="true" />
        <div className="hero__text">
          <h1 id="hero-title">Your group talks.<br />Cadence keeps it moving.</h1>
          <p className="hero__lead">
            Cadence reads your group chat, notices when something needs coordinating, and suggests a next step. Your group decides.
          </p>
          <PromptBar />
          <div className="hero__actions">
            <a className="btn btn--glass btn--large" href="#how">See how it works</a>
            <span className="muted small">In the browser, and in Slack or Discord where the bot is installed.</span>
          </div>
        </div>
        <figure className="hero__art" aria-hidden="true">
          <img src="/brand/hero-hub.webp" width={1448} height={1086} alt="" decoding="async" fetchPriority="high" />
        </figure>
      </section>

      <section className="statement" data-scroll aria-label="In one sentence">
        <p style={{ ["--n" as string]: STATEMENT.length } as CSSProperties}>
          {STATEMENT.map((word, i) => (
            <span key={`${word}-${i}`} className="statement__word" style={{ ["--i" as string]: i } as CSSProperties}>{word} </span>
          ))}
        </p>
      </section>

      <section className="proof" aria-labelledby="proof-title">
        <div className="proof__text">
          <h2 id="proof-title">This is what stepping in looks like.</h2>
          <p>Two messages, a task with no owner. Cadence posts one card with its reason. Try the buttons: it is an example, nothing is saved.</p>
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
          <ProposalCard proposal={EXAMPLE} agentName="Cadence" onAnswer={exampleAnswer} memberName={memberName} />
        </figure>
      </section>

      <section id="how" className="flow" data-scroll aria-labelledby="how-title">
        <header className="flow__head">
          <h2 id="how-title">From a message to a decision, in three steps.</h2>
        </header>
        <div className="flow__grid">
          <div className="flow__track">
            {/* The cadence line: drawn as the page scrolls, one checkpoint per step. */}
            <svg className="flow__line" viewBox="0 0 4 100" preserveAspectRatio="none" aria-hidden="true">
              <line x1="2" y1="0" x2="2" y2="100" className="flow__line-base" />
              <line x1="2" y1="0" x2="2" y2="100" className="flow__line-fill" pathLength={1} />
            </svg>
            <ol className="flow__steps">
              {STORY.map((s, i) => (
                <li key={s.title} ref={(el) => { refs.current[i] = el; }} data-step={i} className={`flow__step${active === i ? " is-active" : ""}${active > i ? " is-done" : ""}`}>
                  <span className="flow__dot" aria-hidden="true">{active > i ? <FontAwesomeIcon icon={faCheck} /> : i + 1}</span>
                  <p className="flow__kicker">{s.kicker}</p>
                  <h3>{s.title}</h3>
                  <p>{s.text}</p>
                  <ul className="bullets">{s.points.map((p) => <li key={p}>{p}</li>)}</ul>
                </li>
              ))}
            </ol>
          </div>
          <div className="flow__stage"><Stage step={active} /></div>
        </div>
      </section>

      <section className="needs" aria-labelledby="needs-title">
        <h2 id="needs-title">Three things that slow every group down.</h2>
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

      <section className="guide" aria-labelledby="guide-title">
        <h2 id="guide-title">Set up in two minutes. Then just talk.</h2>
        <ol>
          {GUIDE.map((g, i) => (
            <li key={g.title}>
              <span className="guide__n" aria-hidden="true">{i + 1}</span>
              <h3>{g.title}</h3>
              <p>{g.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="rule" data-scroll aria-labelledby="rule-title">
        <div className="rule__inner">
          <div className="fan" aria-hidden="true">
            {FAN.map((c, i) => (
              <div key={c.title} className="fan__card" style={{ ["--k" as string]: i - 1 } as CSSProperties}>
                <p className="fan__from"><LogoMark size={16} /> Cadence <em>{c.need}</em></p>
                <p className="fan__title">{c.title}</p>
                <p className="fan__line">{c.line}</p>
              </div>
            ))}
          </div>
          <h2 id="rule-title">Cadence proposes.<br />Your group decides.</h2>
          <ul className="rule__list">{RULES.map((r) => <li key={r}><FontAwesomeIcon icon={faCheck} /> {r}</li>)}</ul>
          <div className="rule__actions">
            <a className="btn btn--primary btn--large" href="/login">Get started</a>
            <a className="btn btn--outline btn--large" href="/login">Log in or create an account</a>
          </div>
        </div>
      </section>

      <footer className="foot">
        <Logo size={22} />
        <p>Cadence is the Group Coordinator prototype of group 17, Advanced User Interfaces 2026–27, Politecnico di Milano.</p>
        <p><a href="/preview/connections">Previews of what comes next</a>, with sample data. Icons by Font Awesome Free (CC BY 4.0).</p>
      </footer>
    </div>
  );
}
