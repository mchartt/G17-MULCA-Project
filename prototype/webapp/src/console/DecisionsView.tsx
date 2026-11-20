// Plan and decisions (Matteo, 20/11): the goal as a compact card (clamped,
// expandable), the deliverables as chips, and the decisions as a searchable
// list, newest first, each with its reason, who and when. Changing the plan
// still goes through a card in the chat ("Edit the plan").
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState } from "react";
import { faMagnifyingGlass, faPenToSquare, faXmark } from "../lib/icons";
import type { MemberId, ProjectState } from "../lib/types";

const when = (unix?: number) =>
  unix ? new Date(unix * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";

export function DecisionsPage({ state, nameOf, onPlan }: { state: ProjectState | null; nameOf: (id?: MemberId | null) => string | undefined; onPlan: () => void }) {
  const [query, setQuery] = useState("");
  const [full, setFull] = useState(false);
  const charter = state?.charter;
  const decisions = [...(state?.decisions ?? [])].sort((a, b) => (b.decided_at ?? 0) - (a.decided_at ?? 0));
  const needle = query.trim().toLowerCase();
  const found = needle
    ? decisions.filter((d) => `${d.question} ${d.choice} ${d.reason ?? ""}`.toLowerCase().includes(needle))
    : decisions;

  return (
    <section className="page decisions-page" aria-label="Plan and decisions">
      <article className="goal-card" aria-labelledby="goal-title">
        <div className="goal-card__head">
          <h3 id="goal-title" className="goal-card__label">Goal</h3>
          <button className="btn btn--soft btn--small" onClick={onPlan}><FontAwesomeIcon icon={faPenToSquare} /> Edit the plan</button>
        </div>
        {charter ? (
          <>
            <p className={`goal-card__text${full ? "" : " goal-card__text--clamped"}`}>{charter.goal}</p>
            {charter.goal.length > 180 && (
              <button className="link-btn" aria-expanded={full} onClick={() => setFull(!full)}>{full ? "Show less" : "Show all"}</button>
            )}
            {(charter.deliverables ?? []).length > 0 && (
              <ul className="chips" aria-label="Deliverables">
                {charter.deliverables!.map((d) => <li key={d} className="chip">{d}</li>)}
              </ul>
            )}
            {charter.confirmed_by !== undefined && <p className="muted small">Confirmed by {nameOf(charter.confirmed_by) ?? "a member"}.</p>}
          </>
        ) : (
          <p className="muted">No goal yet. Paste the assignment from Quick access and Cadence proposes one for you to confirm.</p>
        )}
      </article>

      <section className="decisions" aria-labelledby="decisions-title">
        <div className="decisions__head">
          <h3 id="decisions-title">Decisions <span className="seg__count">{decisions.length}</span></h3>
          {decisions.length > 0 && (
            <div className="search">
              <FontAwesomeIcon icon={faMagnifyingGlass} aria-hidden="true" />
              <label htmlFor="d-search" className="sr-only">Search the decisions</label>
              <input id="d-search" type="search" value={query} placeholder="Search decisions" onChange={(e) => setQuery(e.target.value)} />
              {query && <button className="search__clear" aria-label="Clear the search" onClick={() => setQuery("")}><FontAwesomeIcon icon={faXmark} /></button>}
            </div>
          )}
        </div>
        {decisions.length === 0 ? (
          <p className="muted">No decision recorded yet. When the group closes a choice on a card, it is kept here with who decided and why.</p>
        ) : found.length === 0 ? (
          <p className="muted" role="status">No decision matches “{query.trim()}”.</p>
        ) : (
          <ul className="decision-list">
            {found.map((d) => (
              <li key={d.decision_id ?? `${d.question}-${d.decided_at}`} className="decision">
                <p className="decision__choice">{d.choice}{d.reopened_at ? <span className="tag tag--warn">Reopened</span> : null}</p>
                <p className="decision__question">{d.question}</p>
                {d.reason && <p className="decision__reason">{d.reason}</p>}
                <p className="decision__meta">{[nameOf(d.decided_by) ? `Decided by ${nameOf(d.decided_by)}` : "", when(d.decided_at)].filter(Boolean).join(", ")}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
