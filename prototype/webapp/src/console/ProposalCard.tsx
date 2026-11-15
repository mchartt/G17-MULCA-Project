import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useId, useState, type ReactNode } from "react";
import { faBellSlash, faCheck, faCircleQuestion, faCompass, faHandshake, faThumbsUp, faXmark } from "../lib/icons";
import type { Answer, Click, Proposal } from "../lib/types";

// What each kind of card is called (muca_server docs/PROTOCOL.md, "Group Coordinator").
const KIND_TITLES: Record<string, string> = {
  charter: "Project charter",
  task_owner: "Owner and date",
  delegation: "One person can do this",
  decision: "Close the decision",
  plan: "Plan: who does what",
  checkin: "Check-in",
  blocker: "Something is blocked",
};
const STATUS_WORDS: Record<string, string> = {
  pending: "Waiting for a member to confirm",
  applied: "Confirmed",
  rejected: "Rejected",
  expired: "Expired: nothing was changed",
  snoozed: "Not now: silenced on this topic for 30 minutes",
};
// "Why?": the strategy in plain words (spec S5, S2, S3).
const STRATEGY_WHY: Record<string, string> = {
  cs5_owner_and_date: "An action the group agreed on had no owner or no date.",
  cs2_delegate_simple_task: "Several of you were discussing a task one person can do alone.",
  cs3_close_decision: "The same question had two or more options and no decision.",
  cs7_blockers_dependencies: "Someone is stuck or waiting on other work, and a deadline is at risk.",
};

type Props = {
  proposal: Proposal;
  agentName: string;
  onAnswer: (click: Click) => Promise<Answer>;
  /** Name of a member from their id (suggested owner). */
  memberName?: (id: number) => string;
};

/**
 * A coordinator proposal. Nothing changes in the project until a member clicks.
 * Charter cards were asked for (kickoff); task_owner, delegation and decision
 * cards are proactive (M3) and also have Why?, Helpful (feedback only: it
 * changes nothing, spec FR21) and Not now.
 */
export function ProposalCard({ proposal, agentName, onAnswer, memberName = (id) => `member ${id}` }: Props) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);
  const [thanks, setThanks] = useState<string | null>(null);
  const whyId = useId();
  const { payload, status, kind } = proposal;
  const title = KIND_TITLES[kind] ?? "Proposal";
  const context = payload.context;
  const pending = status === "pending";

  async function answer(click: Click) {
    setBusy(true);
    setNotice(null);
    const result = await onAnswer(click);
    setBusy(false);
    if (result.type === "notice" && !result.ok) setNotice(result.text);
  }

  async function helpful() {
    setBusy(true);
    const result = await onAnswer({ action: "helpful" });
    setBusy(false);
    if (result.type === "notice") (result.ok ? setThanks : setNotice)(result.text);
  }

  return (
    <article className={`card card--${status}`} aria-labelledby={`card-${proposal.proposal_id}`}>
      <header className="card__head">
        <span className="card__from"><FontAwesomeIcon icon={faCompass} /> {agentName}</span>
        <h3 id={`card-${proposal.proposal_id}`} className="card__title">{title}</h3>
      </header>
      {proposal.rationale && <p className="card__why">{proposal.rationale}</p>}
      <CardBody proposal={proposal} memberName={memberName} />
      {context && (
        <section id={whyId} className="card__whybox" aria-label="Why the coordinator stepped in" hidden={!whyOpen}>
          <p><strong>{STRATEGY_WHY[context.strategy_id] ?? context.strategy_id}</strong></p>
          <p className="muted">Topic: {context.topic}</p>
          <ul className="card__evidence">
            {context.evidence.map((e, n) => (
              <li key={n}><span className="card__speaker">{e.speaker}</span> {e.text}</li>
            ))}
          </ul>
        </section>
      )}
      <footer className="card__foot">
        <p className="card__status" role="status">{STATUS_WORDS[status] ?? status}</p>
        {pending && (
          <div className="card__actions">
            <Answers proposal={proposal} busy={busy} answer={answer} />
          </div>
        )}
      </footer>
      {context && (
        <div className="card__meta">
          <button className="link-btn" aria-expanded={whyOpen} aria-controls={whyId} onClick={() => setWhyOpen(!whyOpen)}>
            <FontAwesomeIcon icon={faCircleQuestion} /> Why?
          </button>
          {(pending || status === "applied") && (
            // Feedback on a card the group kept; not on one it rejected or silenced.
            <button className="link-btn" disabled={busy || thanks !== null} onClick={() => void helpful()}>
              <FontAwesomeIcon icon={faThumbsUp} /> {thanks ? "Marked helpful" : "Helpful"}
            </button>
          )}
          {pending && (
            <button className="link-btn" disabled={busy} onClick={() => answer({ action: "not_now" })}>
              <FontAwesomeIcon icon={faBellSlash} /> Not now
            </button>
          )}
        </div>
      )}
      {notice && <p className="card__notice" role="alert">{notice}</p>}
      {thanks && <p className="card__thanks" role="status">{thanks}</p>}
    </article>
  );
}

/** The content of each kind of card. */
function CardBody({ proposal, memberName }: { proposal: Proposal; memberName: (id: number) => string }) {
  const { payload, kind } = proposal;
  if (kind === "task_owner" || kind === "delegation") {
    return (
      <>
        <Field label="Task">{payload.title}</Field>
        <Field label="By">{payload.due_date ? formatDate(payload.due_date) : "no date yet"}</Field>
        {kind === "task_owner" && (
          <Field label="Suggested owner">{payload.owner_id ? memberName(payload.owner_id) : "nobody suggested: anyone can take it"}</Field>
        )}
        {kind === "delegation" && payload.return_to && <Field label="Then back to">{payload.return_to}</Field>}
      </>
    );
  }
  if (kind === "plan") {
    return (
      <ul className="card__items">
        {(payload.items ?? []).map((i) => (
          <li key={i.title}>
            <strong>{i.title}</strong>
            <span className="muted small">
              {i.owner_id ? memberName(i.owner_id) : "anyone"}
              {i.due_date ? ` · ${formatDate(i.due_date)}` : ""}
              {i.reason ? ` · ${i.reason}` : ""}
            </span>
          </li>
        ))}
      </ul>
    );
  }
  if (kind === "checkin") {
    return (
      <div className="card__field">
        <h4>What is late or at risk</h4>
        <ul>{(payload.findings ?? []).map((f) => <li key={f}>{f}</li>)}</ul>
      </div>
    );
  }
  if (kind === "blocker") {
    return (
      <>
        <Field label="Task">{payload.title}</Field>
        {payload.question && <Field label="Question">{payload.question}</Field>}
        {payload.helper_id ? <Field label="Who could help">{memberName(payload.helper_id)}</Field> : null}
      </>
    );
  }
  if (kind === "decision") {
    return (
      <>
        <Field label="Question">{payload.question}</Field>
        <ol className="card__options">
          {(payload.options ?? []).map((o) => (
            <li key={o.label}><strong>{o.label}</strong>{o.argument && <span className="muted"> · {o.argument}</span>}</li>
          ))}
        </ol>
      </>
    );
  }
  return (
    <>
      {payload.goal && <Field label="Goal">{payload.goal}</Field>}
      {!!payload.deliverables?.length && (
        <div className="card__field">
          <h4>Deliverables</h4>
          <ul>{payload.deliverables.map((d) => <li key={d}>{d}</li>)}</ul>
        </div>
      )}
      {!!payload.milestones?.length && (
        <div className="card__field">
          <h4>Milestones</h4>
          <ul>
            {payload.milestones.map((m) => (
              <li key={m.title}>
                {m.title} <span className="muted">{m.due_date ? formatDate(m.due_date) : "no date yet"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

/** The answer buttons of each kind (Why? and Not now are below the card). */
function Answers({ proposal, busy, answer }: { proposal: Proposal; busy: boolean; answer: (c: Click) => void }) {
  const { kind, payload } = proposal;
  const reject = <button className="btn btn--soft" disabled={busy} onClick={() => answer({ action: "reject" })}><FontAwesomeIcon icon={faXmark} /> Reject</button>;
  const take = <button className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "take" })}><FontAwesomeIcon icon={faHandshake} /> I'll take it</button>;
  if (kind === "decision" || kind === "checkin") {
    return (
      <>
        {(payload.options ?? []).map((o, n) => (
          <button key={o.label} className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "choose", option: n })}>{o.label}</button>
        ))}
        {reject}
      </>
    );
  }
  if (kind === "delegation") return <>{take}{reject}</>;
  if (kind === "blocker") {
    return (
      <>
        <button className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "confirm" })}><FontAwesomeIcon icon={faCheck} /> Mark as blocked</button>
        {reject}
      </>
    );
  }
  if (kind === "task_owner") {
    return (
      <>
        {payload.owner_id ? <button className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "confirm" })}><FontAwesomeIcon icon={faCheck} /> Confirm</button> : null}
        {take}
        {reject}
      </>
    );
  }
  return (
    <>
      <button className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "confirm" })}><FontAwesomeIcon icon={faCheck} /> Confirm</button>
      {reject}
    </>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="card__field">
      <h4>{label}</h4>
      <p>{children}</p>
    </div>
  );
}

export function formatDate(iso: string): string {
  const date = new Date(`${iso}T12:00:00`);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
