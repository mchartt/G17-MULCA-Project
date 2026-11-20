import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useId, useState, type ReactNode } from "react";
import { faBellSlash, faCheck, faCircleQuestion, faCompass, faHandshake, faThumbsUp, faXmark } from "../lib/icons";
import type { Answer, Click, Proposal, MemberId } from "../lib/types";

// What each kind of card is called (muca_server docs/PROTOCOL.md, "Group Coordinator").
const KIND_TITLES: Record<string, string> = {
  charter: "Project charter",
  task_owner: "Owner and date",
  delegation: "One person can do this",
  decision: "Close the decision",
  plan: "Plan: who does what",
  checkin: "Check-in",
  blocker: "Something is blocked",
  revisit: "Already decided",
  approach: "How you plan the work",
};
// Which shared need a proactive card answers (the three needs the tutor named
// on 18/11: ownership, dependencies, decisions). Shown as a small label, so
// the group sees what kind of help this is without strategy codes.
const NEED_LABELS: Record<string, string> = {
  cs5_owner_and_date: "Ownership",
  cs2_delegate_simple_task: "Ownership",
  cs7_blockers_dependencies: "Dependency",
  cs3_close_decision: "Decision",
  cs3_reopened_decision: "Decision",
  plan_opener: "Plan",
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
  cs7_blockers_dependencies: "Some work seems to wait on other work that is not ready, and a date is at risk.",
  cs3_reopened_decision: "A choice the group already made, with a reason, was being discussed again.",
  plan_opener: "Cadence asked how you want to plan the work: this is what you answered.",
  // Preview only (src/preview/): MUCA-Server has no such strategy yet.
  cs14_find_a_time: "The group needed a meeting before a deadline and nobody proposed a time.",
};

type Props = {
  proposal: Proposal;
  agentName: string;
  onAnswer: (click: Click) => Promise<Answer>;
  /** Name of a member from their id (suggested owner). */
  memberName?: (id: MemberId) => string;
  /** A title other than the kind's own (the preview's "Find a time" card). */
  title?: string;
};

/**
 * A coordinator proposal. Nothing changes in the project until a member clicks.
 * Charter cards were asked for (kickoff); task_owner, delegation and decision
 * cards are proactive (M3) and also have Why?, Helpful (feedback only: it
 * changes nothing, spec FR21) and Not now.
 */
export function ProposalCard({ proposal, agentName, onAnswer, memberName = (id) => `member ${id}`, title: givenTitle }: Props) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);
  const [thanks, setThanks] = useState<string | null>(null);
  const whyId = useId();
  const { payload, status, kind } = proposal;
  const possible = kind === "blocker" && payload.certainty === "possible";
  const title = givenTitle ?? (possible ? "Possible dependency" : KIND_TITLES[kind]) ?? "Proposal";
  const context = payload.context;
  const pending = status === "pending";
  const need = context ? NEED_LABELS[context.strategy_id] : undefined;

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
        {need && <span className="card__need">{need}</span>}
        {possible && <span className="card__tentative" title="Cadence inferred this from the chat and the plan: confirm it or say no.">Not confirmed yet</span>}
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
        <p className="card__status" role="status">{statusLine(proposal, memberName)}</p>
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
function CardBody({ proposal, memberName }: { proposal: Proposal; memberName: (id: MemberId) => string }) {
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
    const possible = payload.certainty === "possible";
    const waitsOn = typeof payload.depends_on_title === "string" ? payload.depends_on_title : "";
    const ways = Array.isArray(payload.ways_forward) ? (payload.ways_forward as string[]) : [];
    return (
      <>
        <Field label="Task">{payload.title}</Field>
        {waitsOn && <Field label={possible ? "May wait on" : "Waits on"}>{waitsOn}</Field>}
        {waitsOn && payload.depends_on_owner_id ? <Field label="Delivered by">{memberName(payload.depends_on_owner_id)}</Field> : null}
        {payload.question && <Field label="Question">{payload.question}</Field>}
        {payload.helper_id ? <Field label="Who could help">{memberName(payload.helper_id)}</Field> : null}
        {ways.length > 0 && (
          <div className="card__field">
            <h4>Possible ways forward <span className="muted">· ideas, nothing changes by itself</span></h4>
            <ul className="card__ways">{ways.map((w) => <li key={w}>{w}</li>)}</ul>
          </div>
        )}
      </>
    );
  }
  if (kind === "revisit") {
    const newPoint = typeof payload.new_point === "string" ? payload.new_point : "";
    const reason = typeof payload.reason === "string" ? payload.reason : "";
    return (
      <>
        <Field label="Question">{payload.question}</Field>
        <Field label="The group chose">{String(payload.choice ?? "")}</Field>
        {reason && <Field label="Because">{reason}</Field>}
        <Field label="What seems new">{newPoint || "Nothing new so far: the same arguments as before."}</Field>
        <p className="card__ask">Has anything changed? Keep it, or reopen the question.</p>
      </>
    );
  }
  if (kind === "approach") {
    const list = (value: unknown) => (Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []);
    const agreed = list(payload.agreements);
    const open = list(payload.open_points);
    return (
      <>
        <Field label="In short">{String(payload.summary ?? "")}</Field>
        <div className="card__field">
          <h4>What you agreed</h4>
          <ul>{agreed.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
        {open.length > 0 && (
          <div className="card__field">
            <h4>Still open <span className="muted">· raised, not agreed</span></h4>
            <ul>{open.map((o) => <li key={o}>{o}</li>)}</ul>
          </div>
        )}
        <p className="card__ask">Confirm it and it goes to your decisions. You can change it later with “Plan together”.</p>
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
  if (kind === "revisit") {
    // Keep / Reopen it are the two options the server labelled; Not now is below.
    return (
      <>
        {(payload.options ?? []).map((o, n) => (
          <button key={o.label} className={`btn ${n === 0 ? "btn--primary" : "btn--soft"}`} disabled={busy} onClick={() => answer({ action: "choose", option: n })}>{o.label}</button>
        ))}
      </>
    );
  }
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
    if (payload.certainty === "possible") {
      // Nothing is recorded unless someone confirms the dependency is real.
      return (
        <>
          <button className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "confirm" })}><FontAwesomeIcon icon={faCheck} /> Yes, it depends</button>
          <button className="btn btn--soft" disabled={busy} onClick={() => answer({ action: "reject" })}><FontAwesomeIcon icon={faXmark} /> No, it doesn't</button>
        </>
      );
    }
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

/** The status under a card, with who answered it once someone did (the outcome is visible to everyone). */
function statusLine(proposal: Proposal, memberName: (id: MemberId) => string): string {
  const who = proposal.resolved_by != null ? memberName(proposal.resolved_by) : null;
  if (who && proposal.status === "applied") return `Confirmed by ${who}`;
  if (who && proposal.status === "rejected") return `Turned down by ${who}`;
  if (who && proposal.status === "snoozed") return `Not now (${who}): silenced on this topic for 30 minutes`;
  return STATUS_WORDS[proposal.status] ?? proposal.status;
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
