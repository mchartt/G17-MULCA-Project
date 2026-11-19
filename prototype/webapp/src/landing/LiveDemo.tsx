import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState, type CSSProperties, type KeyboardEvent } from "react";
import { ProposalCard } from "../console/ProposalCard";
import { faCheck, faRotate } from "../lib/icons";
import type { Answer, Click, Proposal } from "../lib/types";

type Line = { who: string; color: string; text: string };
type Scenario = {
  need: string;
  chat: Line[];
  card: Proposal;
  /** What the space shows once a member has answered. */
  outcome: (click: Click) => string;
};

const MEMBERS = { 1: "Marco", 2: "Sara", 3: "Ada", 4: "You" };
const color = { Marco: "var(--m1)", Sara: "var(--m2)", Ada: "var(--m3)" };
const evidence = (chat: Line[]) => chat.map((m, i) => ({ speaker: m.who, text: m.text, at_ms: i }));

const OWNER_CHAT: Line[] = [
  { who: "Marco", color: color.Marco, text: "Someone has to write the user test plan before Thursday." },
  { who: "Sara", color: color.Sara, text: "Yes, we can't run the tests without it." },
];
const BLOCKER_CHAT: Line[] = [
  { who: "Ada", color: color.Ada, text: "The API still needs two endpoints, maybe next week." },
  { who: "Sara", color: color.Sara, text: "I planned to test the dashboard on Friday though." },
];
const DECISION_CHAT: Line[] = [
  { who: "Marco", color: color.Marco, text: "Think-aloud or SUS for the user test?" },
  { who: "Sara", color: color.Sara, text: "Think-aloud tells us more. SUS is quicker to run." },
  { who: "Ada", color: color.Ada, text: "We said the same thing yesterday…" },
];

/**
 * Three situations, each the card a real space would show (same component as
 * the console). SCRIPTED: no model runs and nothing leaves the browser.
 */
const SCENARIOS: Scenario[] = [
  {
    need: "Ownership",
    chat: OWNER_CHAT,
    card: {
      proposal_id: "demo-owner",
      kind: "task_owner",
      status: "pending",
      rationale: "Stepping in because this task has no owner yet.",
      payload: {
        title: "Write the user test plan",
        owner_id: 2,
        due_date: "2026-11-27",
        context: { strategy_id: "cs5_owner_and_date", topic: "User test plan", evidence: evidence(OWNER_CHAT) },
      },
    },
    outcome: (c) => (c.action === "take" ? "Added to Tasks: Write the user test plan · You · 27 Nov" : "Added to Tasks: Write the user test plan · Sara · 27 Nov"),
  },
  {
    need: "Dependency",
    chat: BLOCKER_CHAT,
    card: {
      proposal_id: "demo-blocker",
      kind: "blocker",
      status: "pending",
      rationale: "Friday's test waits on work that is not ready.",
      payload: {
        title: "Test the dashboard",
        certainty: "blocked",
        depends_on_title: "Finish the API endpoints",
        ways_forward: ["Test with mock data on Friday", "Move the test to Monday"],
        context: { strategy_id: "cs7_blockers_dependencies", topic: "Dashboard test", evidence: evidence(BLOCKER_CHAT) },
      },
    },
    outcome: () => "In the plan: Test the dashboard waits on Finish the API endpoints",
  },
  {
    need: "Decision",
    chat: DECISION_CHAT,
    card: {
      proposal_id: "demo-decision",
      kind: "decision",
      status: "pending",
      rationale: "The same question came back with two options and no choice.",
      payload: {
        question: "Which method for the user test?",
        options: [
          { label: "Think-aloud", argument: "richer findings" },
          { label: "SUS", argument: "quicker to run" },
        ],
        context: { strategy_id: "cs3_close_decision", topic: "User test method", evidence: evidence(DECISION_CHAT) },
      },
    },
    outcome: (c) => `Added to Decisions: ${c.option === 1 ? "SUS" : "Think-aloud"}, with its reason`,
  },
];

const STATUS_FOR: Partial<Record<Click["action"], Proposal["status"]>> = {
  confirm: "applied",
  take: "applied",
  choose: "applied",
  reject: "rejected",
  not_now: "snoozed",
};

/** The card as it stands after a click: the visitor ("You", id 4) answered it. */
function answered(card: Proposal, click: Click): Proposal {
  return { ...card, status: STATUS_FOR[click.action] ?? card.status, resolved_by: 4 };
}

/** "See it work": pick a situation, read the chat, answer Cadence's card. */
export function LiveDemo() {
  const [pick, setPick] = useState(0);
  const [card, setCard] = useState<Proposal>(SCENARIOS[0].card);
  const [result, setResult] = useState<string | null>(null);
  const [run, setRun] = useState(0); // restarts the chat animation
  const scenario = SCENARIOS[pick];

  const show = (n: number) => {
    setPick(n);
    setCard(SCENARIOS[n].card);
    setResult(null);
    setRun((r) => r + 1);
  };

  // Tabs pattern (WAI-ARIA APG): arrows move between situations, focus follows.
  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (pick + step + SCENARIOS.length) % SCENARIOS.length;
    show(next);
    document.getElementById(`demo-tab-${next}`)?.focus();
  };

  const onAnswer = async (click: Click): Promise<Answer> => {
    if (click.action === "helpful") return { type: "notice", ok: true, text: "Thanks: Cadence will keep stepping in like this." };
    setCard((c) => answered(c, click));
    setResult(STATUS_FOR[click.action] === "applied" ? scenario.outcome(click) : null);
    return { type: "notice", ok: true, text: "" };
  };

  return (
    <div className="demo">
      <div className="demo__tabs" role="tablist" aria-label="Situations" onKeyDown={onTabKey}>
        {SCENARIOS.map((s, n) => (
          <button
            key={s.need}
            id={`demo-tab-${n}`}
            role="tab"
            aria-selected={pick === n}
            aria-controls="demo-panel"
            tabIndex={pick === n ? 0 : -1}
            className="demo__tab"
            onClick={() => show(n)}
          >
            {s.need}
          </button>
        ))}
      </div>

      <div id="demo-panel" role="tabpanel" aria-labelledby={`demo-tab-${pick}`} className="demo__window">
        <div className="demo__bar">
          <span aria-hidden="true"><i /><i /><i /></span>
          <span className="demo__room">AUI group 17 · Group chat</span>
          <button className="demo__again" onClick={() => show(pick)}>
            <FontAwesomeIcon icon={faRotate} /> Play again
          </button>
        </div>
        <div className="demo__log doodles" key={run}>
          {scenario.chat.map((m, i) => (
            <p key={m.text} className="demo__msg" style={{ ["--d" as string]: `${200 + i * 650}ms` } as CSSProperties}>
              <span className="avatar avatar--small" style={{ background: m.color }} aria-hidden="true">{m.who[0]}</span>
              <span><strong>{m.who}</strong> {m.text}</span>
            </p>
          ))}
          <div className="demo__card" style={{ ["--d" as string]: `${400 + scenario.chat.length * 650}ms` } as CSSProperties}>
            <ProposalCard proposal={card} agentName="Cadence" onAnswer={onAnswer} memberName={(id) => MEMBERS[Number(id) as 1] ?? `member ${id}`} />
          </div>
          {result && (
            <p className="demo__done" role="status">
              <FontAwesomeIcon icon={faCheck} /> {result}
            </p>
          )}
        </div>
      </div>
      <p className="demo__note">Example with a script, in your browser: no AI runs here and nothing is saved.</p>
    </div>
  );
}
