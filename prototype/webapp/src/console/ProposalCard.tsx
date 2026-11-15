import { useState } from "react";
import type { Answer, Proposal } from "../lib/types";

const KIND_TITLES: Record<string, string> = { charter: "Project charter" };
const STATUS_WORDS: Record<string, string> = {
  pending: "Waiting for a member to confirm",
  applied: "Confirmed",
  rejected: "Rejected",
  expired: "Expired: nothing was changed",
};

type Props = {
  proposal: Proposal;
  agentName: string;
  onAnswer: (action: "confirm" | "reject") => Promise<Answer>;
};

/** A coordinator proposal. Nothing changes in the project until a member clicks. */
export function ProposalCard({ proposal, agentName, onAnswer }: Props) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const { payload, status } = proposal;
  const title = KIND_TITLES[proposal.kind] ?? "Proposal";

  async function answer(action: "confirm" | "reject") {
    setBusy(true);
    setNotice(null);
    const result = await onAnswer(action);
    setBusy(false);
    if (result.type === "notice" && !result.ok) setNotice(result.text);
  }

  return (
    <article className={`card card--${status}`} aria-labelledby={`card-${proposal.proposal_id}`}>
      <header className="card__head">
        <span className="card__from">{agentName}</span>
        <h3 id={`card-${proposal.proposal_id}`} className="card__title">{title}</h3>
      </header>
      {proposal.rationale && <p className="card__why">{proposal.rationale}</p>}
      {payload.goal && (
        <div className="card__field">
          <h4>Goal</h4>
          <p>{payload.goal}</p>
        </div>
      )}
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
      <footer className="card__foot">
        <p className="card__status" role="status">{STATUS_WORDS[status] ?? status}</p>
        {status === "pending" && (
          <div className="card__actions">
            <button className="btn btn--confirm" disabled={busy} onClick={() => answer("confirm")}>Confirm</button>
            <button className="btn btn--quiet" disabled={busy} onClick={() => answer("reject")}>Reject</button>
          </div>
        )}
      </footer>
      {notice && <p className="card__notice" role="alert">{notice}</p>}
    </article>
  );
}

export function formatDate(iso: string): string {
  const date = new Date(`${iso}T12:00:00`);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
