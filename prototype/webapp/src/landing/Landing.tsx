import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { Logo, LogoMark } from "../brand/Logo";
import { saveDraftBrief } from "../lib/brief";
import { faArrowUp, faCheck } from "../lib/icons";
import { LiveDemo } from "./LiveDemo";
import { Nav } from "./Nav";

// The little chat of "How it works": two messages, then the card Cadence posts (CS5).
const CHAT = [
  { who: "Marco", color: "var(--m1)", text: "Someone has to write the user test plan before Thursday." },
  { who: "Sara", color: "var(--m2)", text: "Yes, we can't run the tests without it." },
];

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

/**
 * The three needs the tutor named on 18/11, as the three cards the hero photo
 * becomes. Each caption says what its picture shows (Matteo's photos, 19/11):
 * someone stuck alone at the laptop, a sprint board, three people arguing it out.
 */
const NEEDS = [
  {
    label: "What waits on what",
    need: "Dependency",
    title: "The dashboard waits on the API",
    line: "Stuck until the API is ready. Cadence flags it before the deadline.",
    img: { src: "/brand/stuck-alone.webp", width: 1182, height: 1150, position: "50% 35%" },
  },
  {
    label: "Who does what",
    need: "Ownership",
    title: "Write the user test plan",
    line: "It sits in To Do with no name on it. Sara could own it, by 27 Nov.",
    img: { src: "/brand/sprint-board.webp", width: 1182, height: 1150, position: "45% 45%" },
  },
  {
    label: "What was decided",
    need: "Decision",
    title: "Think-aloud or SUS?",
    line: "The same two options, argued again. Close it with one click and keep the reasons.",
    img: { src: "/brand/decision-talk.webp", width: 1180, height: 1150, position: "50% 35%" },
  },
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

/**
 * Scroll progress as CSS variables, one rAF per frame:
 *   on the page                --progress (0..1 of the whole page);
 *   on every [data-scroll]     --p   (0 when its top reaches the bottom of the screen, 1 when its bottom leaves the top);
 *   on every [data-pin]        --pin (0 when it reaches the top of the screen, 1 when its sticky part is released).
 * CSS does the rest (the hero's photo, the cadence line, the stage).
 */
function useScrollVars(root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    const page = root.current;
    if (!page) return;
    if (calm()) {
      page.querySelectorAll<HTMLElement>("[data-scroll]").forEach((el) => el.style.setProperty("--p", "1"));
      return;
    }
    const clamp01 = (n: number) => String(Math.max(0, Math.min(1, n)));
    let frame = 0;
    const update = () => {
      frame = 0;
      const max = document.documentElement.scrollHeight - innerHeight;
      page.style.setProperty("--progress", clamp01(max > 0 ? scrollY / max : 0));
      page.querySelectorAll<HTMLElement>("[data-scroll]").forEach((el) => {
        const r = el.getBoundingClientRect();
        el.style.setProperty("--p", clamp01((innerHeight - r.top) / (innerHeight + r.height)));
      });
      page.querySelectorAll<HTMLElement>("[data-pin]").forEach((el) => {
        const r = el.getBoundingClientRect();
        const run = r.height - innerHeight;
        el.style.setProperty("--pin", clamp01(run > 0 ? -r.top / run : 0));
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
        <div className="stage__body doodles">
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
            <FontAwesomeIcon icon={faCheck} /> <span>Sara confirmed. Added to Tasks: <strong>Write the user test plan</strong>, Sara, 27 Nov</span>
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

/**
 * The opening, in the manner of a scroll film: the group's photo fills the
 * screen with the headline; scrolling, it shrinks into the middle card of
 * three, one per coordination need. Small screens and reduced motion get the
 * same content stacked, without pinning (brand.css).
 */
function Reel() {
  return (
    <section className="reel" data-pin aria-labelledby="hero-title">
      <div className="reel__pin">
        <div className="reel__photo" aria-hidden="true">
          <img src="/brand/group-at-laptop.webp" width={1672} height={941} alt="" decoding="async" fetchPriority="high" />
        </div>
        <div className="reel__intro">
          <div className="reel__copy">
            <h1 id="hero-title">Your group talks. Cadence keeps it moving.</h1>
            <p className="reel__lead">
              Cadence reads your group chat, notices when something needs coordinating, and suggests a next step. Your group decides.
            </p>
            <PromptBar />
            <div className="reel__actions">
              <a className="btn btn--glass btn--large" href="#demo">Try the demo</a>
              <span className="reel__where">In the browser, and in Slack or Discord where the bot is installed.</span>
            </div>
          </div>
        </div>
        <header className="reel__after">
          <h2 id="needs-title">Three things that slow every group down.</h2>
          <p>Cadence notices them in the chat and suggests the next step, with its reason.</p>
        </header>
        <ul className="reel__row" aria-labelledby="needs-title">
          {NEEDS.map((n, i) => (
            <li key={n.need} className={`reel__card${i === 1 ? " reel__card--main" : ""}`} style={{ ["--k" as string]: i - 1 } as CSSProperties}>
              <div className="reel__media">
                <img className="reel__img" src={n.img.src} style={{ objectPosition: n.img.position }} width={n.img.width} height={n.img.height} alt="" loading={i === 1 ? "eager" : "lazy"} decoding="async" />
                <h3 className="reel__label">{n.label}</h3>
              </div>
              <div className="reel__chip">
                <p className="reel__from"><LogoMark size={16} /> Cadence <em>{n.need}</em></p>
                <p className="reel__title">{n.title}</p>
                <p className="reel__line">{n.line}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/** The public page: what Cadence does, a demo to try, how it works, how to start. Every way in leads to /login. */
export function Landing() {
  const page = useRef<HTMLDivElement>(null);
  useScrollVars(page);
  const { active, refs } = useActiveStep(STORY.length);

  return (
    <div className="landing" id="top" ref={page}>
      <div className="progress" aria-hidden="true" />
      <Nav />

      <Reel />

      <section id="demo" className="band doodles" aria-labelledby="demo-title">
        <div className="tryit">
          <div className="tryit__text">
            <h2 id="demo-title">Try it: answer Cadence's card.</h2>
            <p>Pick a situation. Two or three messages arrive, then the card Cadence would post in your group. Confirm, choose, or say “not now”, and see what changes.</p>
          </div>
          <LiveDemo />
        </div>
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

      <section className="band doodles" aria-labelledby="guide-title">
        <div className="guide">
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
        </div>
      </section>

      <section className="rule" aria-labelledby="rule-title">
        <div className="rule__inner">
          <span className="rule__mark" aria-hidden="true"><LogoMark size={28} /></span>
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
