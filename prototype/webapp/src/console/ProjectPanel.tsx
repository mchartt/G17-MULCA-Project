import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faBullseye, faCalendarCheck, faCalendarDays, faFileLines, faFlag, faListCheck, faRotate, faScaleBalanced, faUserPen, faUsers } from "../lib/icons";
import { useState, type FormEvent } from "react";
import type { Person, ProjectState, MemberId, Names } from "../lib/types";
import { formatDate } from "./ProposalCard";
import { DoneBox } from "./PlanDialogs";
import { nextMilestones, todayIso, upNext, type TaskEdit } from "./plan";
import { dotFor, nameOf as spaceNameOf } from "./space";

type Props = {
  state: ProjectState | null;
  members: Person[];
  names?: Names;
  onKickoff: () => void;
  onRefresh: () => void;
  /** A member changes a task by hand: done or not, its owner (their own action, no card). */
  onTask?: (taskId: string, edit: TaskEdit) => void;
  /** Open one of the plan's own pages: every task, the plan day by day, the milestones. */
  onOpen?: (page: "tasks" | "agenda" | "milestones") => void;
  /** M4: "why did we decide X?"; resolves to the answer with its source. */
  onWhy?: (question: string) => Promise<string>;
  /** M5: create a private calendar feed link (milestones and task dates). */
  onCalendar?: () => Promise<string>;
  /** The member looking at the panel: their row in Team gets "Edit". */
  me?: MemberId | null;
  onProfile?: () => void;
  /** The language Cadence writes in for this group: "en", "it" or "" (it follows the chat). */
  onLanguage?: (language: string) => void;
  /** A member rewrites goal and deliverables; resolves to an error to show, or null (a card was posted). */
  onCharter?: (goal: string, deliverables: string[]) => Promise<string | null>;
};

// The panel is the quick view next to the chat: what comes next, not the archive.
const TASKS_SHOWN = 5;
const MILESTONES_SHOWN = 3;
const DECISIONS_SHOWN = 2;
const TEAM_SHOWN = 4;

/** The plan as the group agreed it: always visible next to the chat (UC9). */
export function ProjectPanel({ state, members, names = {}, onKickoff, onRefresh, onTask, onOpen, onWhy, onCalendar, me = null, onProfile, onLanguage, onCharter }: Props) {
  const charter = state?.charter;
  const [editing, setEditing] = useState(false);
  const [allDecisions, setAllDecisions] = useState(false);
  const tasks = state?.tasks ?? [];
  const next = upNext(tasks, TASKS_SHOWN);
  const done = tasks.length - next.open;
  const milestones = state?.milestones ?? [];
  const ahead = nextMilestones(milestones, todayIso(), MILESTONES_SHOWN);
  const decisions = state?.decisions ?? [];
  const shownDecisions = allDecisions ? decisions : decisions.slice(-DECISIONS_SHOWN);
  const nameOf = (id?: MemberId | null) => spaceNameOf(id, { members, names });

  return (
    <aside className="panel" aria-labelledby="panel-title">
      <div className="panel__head">
        <h2 id="panel-title">Project plan</h2>
        <button className="btn btn--soft btn--small" onClick={onRefresh}><FontAwesomeIcon icon={faRotate} /> Refresh</button>
      </div>

      {/* The goal waits for the kickoff; tasks and decisions can come before it (M3 cards). */}
      {!charter ? (
        <div className="panel__empty">
          <p>No goal yet. Paste the assignment and Cadence proposes a goal, deliverables and milestones for the group to confirm.</p>
          <button className="btn btn--primary" onClick={onKickoff}><FontAwesomeIcon icon={faFileLines} /> Paste the assignment</button>
        </div>
      ) : (
        <section className="panel__section panel-card">
          <h3><FontAwesomeIcon icon={faBullseye} /> Goal</h3>
          {editing && onCharter ? (
            <GoalForm goal={charter.goal} deliverables={charter.deliverables ?? []} onSave={onCharter} onClose={() => setEditing(false)} />
          ) : (
            <>
              <p className="panel__goal">{charter.goal}</p>
              {!!charter.deliverables?.length && (
                <>
                  <p className="muted small panel__label">Deliverables</p>
                  <ul className="panel__list">
                    {charter.deliverables.map((d) => <li key={d}>{d}</li>)}
                  </ul>
                </>
              )}
              <p className="muted small panel__foot">
                {charter.confirmed_by && <span>Confirmed by {nameOf(charter.confirmed_by) ?? "a member"}</span>}
                {onCharter && <button className="link-btn" onClick={() => setEditing(true)}>Edit goal</button>}
              </p>
            </>
          )}
        </section>
      )}
      <section className="panel__section panel-card">
        <h3><FontAwesomeIcon icon={faListCheck} /> Up next</h3>
        {next.shown.length ? (
          <ul className="tasks">
            {next.shown.map((t) => {
              const mine = me !== null && String(t.owner_id) === String(me);
              return (
                <li key={t.task_id ?? t.title}>
                  {onTask ? <DoneBox task={t} onTask={onTask} /> : <span className="dot" style={{ background: t.owner_id ? dotFor(t.owner_id, members) : "var(--line)" }} aria-hidden="true" />}
                  <span className="tasks__title">{t.title}</span>
                  <span className="tasks__meta">
                    {t.owner_id ? (
                      <span className="muted small"><span className="dot dot--small" style={{ background: dotFor(t.owner_id, members) }} aria-hidden="true" /> {mine ? "You" : nameOf(t.owner_id) ?? "member"}</span>
                    ) : (
                      <span className="tag tag--warn">No owner</span>
                    )}
                    {t.due_date && <span className="muted small">{formatDate(t.due_date)}</span>}
                    {t.status !== "todo" && <span className="tag">{t.status}</span>}
                    {!t.owner_id && onTask && t.task_id && me !== null && (
                      <button className="link-btn" onClick={() => onTask(t.task_id!, { owner: me })}>I'll take it</button>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="muted">{tasks.length ? "Every task is done." : "No tasks yet. Plan the work together, or add a task by hand."}</p>
        )}
        <p className="panel__foot muted small">
          <span>{next.open > next.shown.length ? `${next.open - next.shown.length} more open` : `${next.open} open`}{done ? ` · ${done} done` : ""}</span>
          {onOpen && (
            <span className="panel__links">
              <button className="link-btn" onClick={() => onOpen("agenda")}><FontAwesomeIcon icon={faCalendarDays} /> Day by day</button>
              <button className="link-btn" onClick={() => onOpen("tasks")}>All tasks</button>
            </span>
          )}
        </p>
      </section>

      <section className="panel__section panel-card">
        <h3><FontAwesomeIcon icon={faFlag} /> Milestones</h3>
        {ahead.length ? (
          <ol className="timeline">
            {ahead.map((m) => (
              <li key={m.milestone_id ?? m.title}>
                <span className="timeline__date">{m.due_date ? formatDate(m.due_date) : "no date"}</span>
                <span>{m.title}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="muted">{milestones.length ? "No milestone ahead." : "No milestones yet."}</p>
        )}
        <p className="panel__foot muted small">
          <span>{milestones.length > ahead.length ? `${milestones.length} in all` : ""}</span>
          {onOpen && <button className="link-btn" onClick={() => onOpen("milestones")}>{milestones.length ? "Edit milestones" : "Add a milestone"}</button>}
        </p>
        {onCalendar && <CalendarLink onCalendar={onCalendar} />}
      </section>

      <Team state={state} members={members} me={me} onProfile={onProfile} onLanguage={onLanguage} />

      <section className="panel__section panel-card">
        <h3><FontAwesomeIcon icon={faScaleBalanced} /> Decisions</h3>
        {decisions.length ? (
          <ul className="decisions">
            {shownDecisions.map((d) => (
              <li key={d.question}>
                <p>{d.question}</p>
                <p className="decisions__choice">{d.choice}</p>
                {d.reason && <p className="muted small">{d.reason}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No decisions recorded yet.</p>
        )}
        {decisions.length > DECISIONS_SHOWN && (
          <button className="link-btn" onClick={() => setAllDecisions(!allDecisions)}>{allDecisions ? "Show the latest only" : `Show all ${decisions.length}`}</button>
        )}
        {onWhy && !!decisions.length && <AskWhy onWhy={onWhy} />}
      </section>
    </aside>
  );
}

/**
 * A member rewrites the goal and the deliverables. Saving does not change the
 * plan: it posts a charter card in the chat, saved when a member confirms it.
 */
function GoalForm({ goal, deliverables, onSave, onClose }: { goal: string; deliverables: string[]; onSave: (goal: string, deliverables: string[]) => Promise<string | null>; onClose: () => void }) {
  const [text, setText] = useState(goal);
  const [list, setList] = useState(deliverables.join("\n"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    const result = await onSave(text.trim(), list.split("\n").map((d) => d.trim()).filter(Boolean));
    setBusy(false);
    setError(result);
    if (!result) onClose();
  }

  return (
    <form className="form goalform" onSubmit={submit}>
      <label htmlFor="goal-text">Goal</label>
      <textarea id="goal-text" rows={5} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} required />
      <label htmlFor="goal-deliverables">Deliverables, one per line</label>
      <textarea id="goal-deliverables" rows={3} value={list} onChange={(e) => setList(e.target.value)} />
      <p className="muted small">Your change becomes a card in the chat. It is saved when a member confirms it.</p>
      {error && <p className="form__error" role="alert">{error}</p>}
      <div className="form__actions">
        <button type="button" className="btn btn--soft btn--small" onClick={onClose}>Cancel</button>
        <button type="submit" className="btn btn--primary btn--small" disabled={busy || !text.trim()}>{busy ? "Sending…" : "Propose change"}</button>
      </div>
    </form>
  );
}

const LANGUAGES = [
  { value: "", label: "Follow the chat" },
  { value: "en", label: "English" },
  { value: "it", label: "Italiano" },
];

/**
 * Who is in the group and what each person wrote about themselves. Cadence
 * suggests task owners from these profiles, so an empty one is said plainly.
 * Each person edits only their own. Below: the language Cadence writes in.
 */
function Team({ state, members, me, onProfile, onLanguage }: Pick<Props, "state" | "members" | "me" | "onProfile" | "onLanguage">) {
  const profiles = state?.members ?? [];
  // Web members first, then members known only from a linked channel's profile.
  const rows = [
    ...members.map((m) => ({ id: m.id as MemberId, name: m.name, profile: profiles.find((p) => String(p.member_id) === String(m.id)) })),
    ...profiles.filter((p) => !members.some((m) => String(m.id) === String(p.member_id))).map((p) => ({ id: p.member_id ?? p.display_name, name: p.display_name, profile: p })),
  ];
  const [all, setAll] = useState(false);
  if (rows.length === 0) return null;
  // The viewer first, so "Edit my profile" is never hidden behind "Show all".
  const ordered = [...rows].sort((a, b) => Number(String(b.id) === String(me)) - Number(String(a.id) === String(me)));
  const shown = all ? ordered : ordered.slice(0, TEAM_SHOWN);

  return (
    <section className="panel__section panel-card">
      <h3><FontAwesomeIcon icon={faUsers} /> Team</h3>
      <ul className="team">
        {shown.map((row) => {
          const p = row.profile;
          const mine = me !== null && String(row.id) === String(me);
          const facts = [p?.discipline?.trim(), p?.skills?.length ? p.skills.join(", ") : "", typeof p?.weekly_hours === "number" ? `${p.weekly_hours} h/week` : ""].filter(Boolean);
          return (
            <li key={String(row.id)}>
              <span className="dot" style={{ background: dotFor(row.id, members) }} aria-hidden="true" />
              <span className="team__name">{row.name}{mine && <span className="tag">You</span>}</span>
              <span className="muted small">{facts.length ? facts.join(" · ") : "No profile yet"}</span>
              {p?.background?.trim() && <span className="muted small team__background">{p.background}</span>}
              {mine && onProfile && (
                <button className="link-btn" onClick={onProfile}><FontAwesomeIcon icon={faUserPen} /> {facts.length ? "Edit my profile" : "Fill in my profile"}</button>
              )}
            </li>
          );
        })}
      </ul>
      {rows.length > TEAM_SHOWN && (
        <button className="link-btn" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${rows.length} members`}</button>
      )}
      {onLanguage && (
        <div className="team__language">
          <label htmlFor="team-language" className="small">Cadence writes in</label>
          <select id="team-language" className="tasks__status" value={state?.language ?? ""} onChange={(e) => onLanguage(e.target.value)}>
            {LANGUAGES.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
          </select>
        </div>
      )}
    </section>
  );
}

/** UC9: ask about a past decision; the answer cites the decision log. */
function AskWhy({ onWhy }: { onWhy: (q: string) => Promise<string> }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setAnswer(await onWhy(question.trim()));
    setBusy(false);
  }

  return (
    <form className="askwhy" onSubmit={submit}>
      <label htmlFor="askwhy-q" className="small">Ask why the group decided something</label>
      <div className="askwhy__row">
        <input id="askwhy-q" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Why did we choose…?" />
        <button className="btn btn--soft btn--small" type="submit" disabled={busy || !question.trim()}>{busy ? "Looking…" : "Ask"}</button>
      </div>
      {answer && <p className="askwhy__answer" role="status">{answer}</p>}
    </form>
  );
}

/** N3: milestones and task dates in each member's own calendar, read-only. */
function CalendarLink({ onCalendar }: { onCalendar: () => Promise<string> }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function make() {
    setError(null);
    setCopied(false);
    try {
      setUrl(await onCalendar());
    } catch (e) {
      setError(e instanceof Error ? e.message : "The link could not be created.");
    }
  }

  return (
    <div className="calendar">
      <button className="btn btn--soft btn--small" onClick={() => void make()}>
        <FontAwesomeIcon icon={faCalendarCheck} /> {url ? "Make a new link" : "Add to my calendar"}
      </button>
      {url && (
        <>
          <label htmlFor="calendar-url" className="small">Subscribe to this link (Google Calendar: Other calendars, From URL; Outlook: Add calendar, Subscribe from web). Keep it private; a new link turns this one off.</label>
          <div className="askwhy__row">
            <input id="calendar-url" readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
            <button className="btn btn--soft btn--small" onClick={() => void navigator.clipboard?.writeText(url).then(() => setCopied(true))}>{copied ? "Copied" : "Copy"}</button>
          </div>
        </>
      )}
      {error && <p className="form__error" role="alert">{error}</p>}
    </div>
  );
}
