import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useId, useState, type ReactNode } from "react";
import { faBellSlash, faCheck, faCircleQuestion, faCompass, faHandshake, faThumbsUp, faXmark } from "../lib/icons";
import { cardLang } from "../lib/lang";
import type { Answer, Click, Proposal, MemberId } from "../lib/types";
import { inline } from "../lib/agentText";

// Every word on a card, in the two languages Cadence writes in. The card's
// own language comes from cardLang (the group's choice, else what Cadence
// wrote on it), so an Italian group no longer gets "Reject" and "Why?".
const WORDS = {
  en: {
    // What each kind of card is called (muca_server docs/PROTOCOL.md, "Group Coordinator").
    kinds: {
      charter: "Project charter",
      task_owner: "Owner and date",
      delegation: "One person can do this",
      decision: "Close the decision",
      plan: "Plan: who does what",
      checkin: "Check-in",
      blocker: "Something is blocked",
      revisit: "Already decided",
      approach: "How you plan the work",
    } as Record<string, string>,
    // A check-in card a member asked for in words ("Cadence, mark X at 50%").
    update: "Update a task",
    possible: "Possible dependency",
    proposal: "Proposal",
    // Which shared need a proactive card answers (the three needs the tutor named
    // on 18/11: ownership, dependencies, decisions). Shown as a small label, so
    // the group sees what kind of help this is without strategy codes.
    needs: {
      cs5_owner_and_date: "Ownership",
      cs2_delegate_simple_task: "Ownership",
      cs7_blockers_dependencies: "Dependency",
      cs3_close_decision: "Decision",
      cs3_reopened_decision: "Decision",
      plan_opener: "Plan",
    } as Record<string, string>,
    status: {
      pending: "Waiting for a member to confirm",
      applied: "Confirmed",
      rejected: "Rejected",
      expired: "Expired: nothing was changed",
      snoozed: "Not now: silenced on this topic for 30 minutes",
    } as Record<string, string>,
    confirmedBy: (who: string) => `Confirmed by ${who}`,
    turnedDownBy: (who: string) => `Turned down by ${who}`,
    snoozedBy: (who: string) => `Not now (${who}): silenced on this topic for 30 minutes`,
    // "Why?": the strategy in plain words (spec S5, S2, S3).
    why: {
      cs5_owner_and_date: "An action the group agreed on had no owner or no date.",
      cs2_delegate_simple_task: "Several of you were discussing a task one person can do alone.",
      cs3_close_decision: "The same question had two or more options and no decision.",
      cs7_blockers_dependencies: "Some work seems to wait on other work that is not ready, and a date is at risk.",
      cs3_reopened_decision: "A choice the group already made, with a reason, was being discussed again.",
      plan_opener: "Cadence asked how you want to plan the work: this is what you answered.",
      // Preview only (src/preview/): MUCA-Server has no such strategy yet.
      cs14_find_a_time: "The group needed a meeting before a deadline and nobody proposed a time.",
    } as Record<string, string>,
    tentative: "Not confirmed yet",
    tentativeHint: "Cadence inferred this from the chat and the plan: confirm it or say no.",
    whyBox: "Why the coordinator stepped in",
    topic: "Topic",
    whyButton: "Why?",
    helpful: "Helpful",
    markedHelpful: "Marked helpful",
    notNow: "Not now",
    confirm: "Confirm",
    reject: "Reject",
    take: "I'll take it",
    yesDepends: "Yes, it depends",
    noDepends: "No, it doesn't",
    markBlocked: "Mark as blocked",
    task: "Task",
    by: "By",
    noDate: "no date yet",
    suggestedOwner: "Suggested owner",
    nobodySuggested: "nobody suggested: anyone can take it",
    backTo: "Then back to",
    anyone: "anyone",
    atRisk: "What is late or at risk",
    asked: "What was asked",
    mayWaitOn: "May wait on",
    waitsOn: "Waits on",
    deliveredBy: "Delivered by",
    question: "Question",
    whoCouldHelp: "Who could help",
    waysForward: "Possible ways forward",
    waysNote: "· ideas, nothing changes by itself",
    groupChose: "The group chose",
    because: "Because",
    whatSeemsNew: "What seems new",
    nothingNew: "Nothing new so far: the same arguments as before.",
    revisitAsk: "Has anything changed? Keep it, or reopen the question.",
    inShort: "In short",
    agreed: "What you agreed",
    stillOpen: "Still open",
    stillOpenNote: "· raised, not agreed",
    approachAsk: "Confirm it and it goes to your decisions. You can change it later with “Plan together”.",
    goal: "Goal",
    deliverables: "Deliverables",
    milestones: "Milestones",
    locale: "en-GB",
  },
  it: {
    kinds: {
      charter: "Charter del progetto",
      task_owner: "Responsabile e data",
      delegation: "Basta una persona",
      decision: "Chiudere la decisione",
      plan: "Piano: chi fa cosa",
      checkin: "Punto della situazione",
      blocker: "Qualcosa è bloccato",
      revisit: "Già deciso",
      approach: "Come pianificate il lavoro",
    } as Record<string, string>,
    update: "Aggiornare un'attività",
    possible: "Possibile dipendenza",
    proposal: "Proposta",
    needs: {
      cs5_owner_and_date: "Responsabile",
      cs2_delegate_simple_task: "Responsabile",
      cs7_blockers_dependencies: "Dipendenza",
      cs3_close_decision: "Decisione",
      cs3_reopened_decision: "Decisione",
      plan_opener: "Piano",
    } as Record<string, string>,
    status: {
      pending: "In attesa che un membro confermi",
      applied: "Confermata",
      rejected: "Rifiutata",
      expired: "Scaduta: non è cambiato nulla",
      snoozed: "Non ora: niente suggerimenti su questo per 30 minuti",
    } as Record<string, string>,
    confirmedBy: (who: string) => `Confermata da ${who}`,
    turnedDownBy: (who: string) => `Rifiutata da ${who}`,
    snoozedBy: (who: string) => `Non ora (${who}): niente suggerimenti su questo per 30 minuti`,
    why: {
      cs5_owner_and_date: "Un'azione su cui il gruppo era d'accordo non aveva un responsabile o una data.",
      cs2_delegate_simple_task: "Ne stavate discutendo in tanti, ma è un'attività che può fare una persona sola.",
      cs3_close_decision: "La stessa domanda aveva due o più opzioni e nessuna decisione.",
      cs7_blockers_dependencies: "Un lavoro sembra aspettarne un altro non ancora pronto, e una data è a rischio.",
      cs3_reopened_decision: "Una scelta già fatta dal gruppo, con un motivo, era di nuovo in discussione.",
      plan_opener: "Cadence vi ha chiesto come volete pianificare il lavoro: questo è quello che avete risposto.",
      cs14_find_a_time: "Serviva un incontro prima di una scadenza e nessuno aveva proposto un orario.",
    } as Record<string, string>,
    tentative: "Ancora da confermare",
    tentativeHint: "Cadence l'ha dedotto dalla chat e dal piano: confermatelo o dite di no.",
    whyBox: "Perché Cadence è intervenuto",
    topic: "Argomento",
    whyButton: "Perché?",
    helpful: "Utile",
    markedHelpful: "Segnata come utile",
    notNow: "Non ora",
    confirm: "Conferma",
    reject: "Rifiuta",
    take: "Me ne occupo io",
    yesDepends: "Sì, dipende",
    noDepends: "No, non dipende",
    markBlocked: "Segna come bloccata",
    task: "Attività",
    by: "Entro",
    noDate: "nessuna data",
    suggestedOwner: "Responsabile proposto",
    nobodySuggested: "nessuno proposto: chiunque può prenderla",
    backTo: "Poi torna a",
    anyone: "chiunque",
    atRisk: "Cosa è in ritardo o a rischio",
    asked: "Cosa è stato chiesto",
    mayWaitOn: "Potrebbe aspettare",
    waitsOn: "Aspetta",
    deliveredBy: "Consegna di",
    question: "Domanda",
    whoCouldHelp: "Chi potrebbe aiutare",
    waysForward: "Possibili strade",
    waysNote: "· idee, non cambia nulla da solo",
    groupChose: "Il gruppo ha scelto",
    because: "Perché",
    whatSeemsNew: "Cosa sembra nuovo",
    nothingNew: "Per ora niente di nuovo: gli stessi argomenti di prima.",
    revisitAsk: "È cambiato qualcosa? Tenetela, o riaprite la domanda.",
    inShort: "In breve",
    agreed: "Su cosa siete d'accordo",
    stillOpen: "Ancora aperto",
    stillOpenNote: "· detto, non concordato",
    approachAsk: "Confermatela e finisce nelle vostre decisioni. Potete cambiarla dopo con “Plan together”.",
    goal: "Obiettivo",
    deliverables: "Consegne",
    milestones: "Scadenze",
    locale: "it-IT",
  },
};
type Words = (typeof WORDS)["en"];

type Props = {
  proposal: Proposal;
  agentName: string;
  onAnswer: (click: Click) => Promise<Answer>;
  /** Name of a member from their id (suggested owner). */
  memberName?: (id: MemberId) => string;
  /** A title other than the kind's own (the preview's "Find a time" card). */
  title?: string;
  /** The language the group chose ("en", "it", "" = follow what Cadence wrote on the card). */
  language?: string;
};

/**
 * A coordinator proposal. Nothing changes in the project until a member clicks.
 * Charter cards were asked for (kickoff); task_owner, delegation and decision
 * cards are proactive (M3) and also have Why?, Helpful (feedback only: it
 * changes nothing, spec FR21) and Not now.
 */
export function ProposalCard({ proposal, agentName, onAnswer, memberName = (id) => `member ${id}`, title: givenTitle, language = "" }: Props) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);
  const [thanks, setThanks] = useState<string | null>(null);
  const whyId = useId();
  const { payload, status, kind } = proposal;
  const w = WORDS[cardLang(proposal, language)];
  const possible = kind === "blocker" && payload.certainty === "possible";
  const requested = kind === "checkin" && payload.requested === true;
  const title = givenTitle ?? (possible ? w.possible : requested ? w.update : w.kinds[kind]) ?? w.proposal;
  const context = payload.context;
  const pending = status === "pending";
  const need = context ? w.needs[context.strategy_id] : undefined;

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
        {possible && <span className="card__tentative" title={w.tentativeHint}>{w.tentative}</span>}
      </header>
      {proposal.rationale && <p className="card__why">{rich(proposal.rationale)}</p>}
      <CardBody proposal={proposal} memberName={memberName} w={w} />
      {context && (
        <section id={whyId} className="card__whybox" aria-label={w.whyBox} hidden={!whyOpen}>
          <p><strong>{w.why[context.strategy_id] ?? context.strategy_id}</strong></p>
          <p className="muted">{w.topic}: {context.topic}</p>
          <ul className="card__evidence">
            {context.evidence.map((e, n) => (
              <li key={n}><span className="card__speaker">{e.speaker}</span> {e.text}</li>
            ))}
          </ul>
        </section>
      )}
      <footer className="card__foot">
        <p className="card__status" role="status">{statusLine(proposal, memberName, w)}</p>
        {pending && (
          <div className="card__actions">
            <Answers proposal={proposal} busy={busy} answer={answer} w={w} />
          </div>
        )}
      </footer>
      {context && (
        <div className="card__meta">
          <button className="link-btn" aria-expanded={whyOpen} aria-controls={whyId} onClick={() => setWhyOpen(!whyOpen)}>
            <FontAwesomeIcon icon={faCircleQuestion} /> {w.whyButton}
          </button>
          {(pending || status === "applied") && (
            // Feedback on a card the group kept; not on one it rejected or silenced.
            <button className="link-btn" disabled={busy || thanks !== null} onClick={() => void helpful()}>
              <FontAwesomeIcon icon={faThumbsUp} /> {thanks ? w.markedHelpful : w.helpful}
            </button>
          )}
          {pending && (
            <button className="link-btn" disabled={busy} onClick={() => answer({ action: "not_now" })}>
              <FontAwesomeIcon icon={faBellSlash} /> {w.notNow}
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
function CardBody({ proposal, memberName, w }: { proposal: Proposal; memberName: (id: MemberId) => string; w: Words }) {
  const { payload, kind } = proposal;
  if (kind === "task_owner" || kind === "delegation") {
    return (
      <>
        <Field label={w.task}>{payload.title}</Field>
        <Field label={w.by}>{payload.due_date ? formatDate(payload.due_date, w.locale) : w.noDate}</Field>
        {kind === "task_owner" && (
          <Field label={w.suggestedOwner}>{payload.owner_id ? memberName(payload.owner_id) : w.nobodySuggested}</Field>
        )}
        {kind === "delegation" && payload.return_to && <Field label={w.backTo}>{payload.return_to}</Field>}
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
              {i.owner_id ? memberName(i.owner_id) : w.anyone}
              {i.due_date ? ` · ${formatDate(i.due_date, w.locale)}` : ""}
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
        <h4>{payload.requested === true ? w.asked : w.atRisk}</h4>
        <ul>{(payload.findings ?? []).map((f) => <li key={f}>{rich(f)}</li>)}</ul>
      </div>
    );
  }
  if (kind === "blocker") {
    const possible = payload.certainty === "possible";
    const waitsOn = typeof payload.depends_on_title === "string" ? payload.depends_on_title : "";
    const ways = Array.isArray(payload.ways_forward) ? (payload.ways_forward as string[]) : [];
    return (
      <>
        <Field label={w.task}>{payload.title}</Field>
        {waitsOn && <Field label={possible ? w.mayWaitOn : w.waitsOn}>{waitsOn}</Field>}
        {waitsOn && payload.depends_on_owner_id ? <Field label={w.deliveredBy}>{memberName(payload.depends_on_owner_id)}</Field> : null}
        {payload.question && <Field label={w.question}>{payload.question}</Field>}
        {payload.helper_id ? <Field label={w.whoCouldHelp}>{memberName(payload.helper_id)}</Field> : null}
        {ways.length > 0 && (
          <div className="card__field">
            <h4>{w.waysForward} <span className="muted">{w.waysNote}</span></h4>
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
        <Field label={w.question}>{payload.question}</Field>
        <Field label={w.groupChose}>{String(payload.choice ?? "")}</Field>
        {reason && <Field label={w.because}>{reason}</Field>}
        <Field label={w.whatSeemsNew}>{newPoint || w.nothingNew}</Field>
        <p className="card__ask">{w.revisitAsk}</p>
      </>
    );
  }
  if (kind === "approach") {
    const list = (value: unknown) => (Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : []);
    const agreed = list(payload.agreements);
    const open = list(payload.open_points);
    return (
      <>
        <Field label={w.inShort}>{String(payload.summary ?? "")}</Field>
        <div className="card__field">
          <h4>{w.agreed}</h4>
          <ul>{agreed.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
        {open.length > 0 && (
          <div className="card__field">
            <h4>{w.stillOpen} <span className="muted">{w.stillOpenNote}</span></h4>
            <ul>{open.map((o) => <li key={o}>{o}</li>)}</ul>
          </div>
        )}
        <p className="card__ask">{w.approachAsk}</p>
      </>
    );
  }
  if (kind === "decision") {
    return (
      <>
        <Field label={w.question}>{payload.question}</Field>
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
      {payload.goal && <Field label={w.goal}>{payload.goal}</Field>}
      {!!payload.deliverables?.length && (
        <div className="card__field">
          <h4>{w.deliverables}</h4>
          <ul>{payload.deliverables.map((d) => <li key={d}>{d}</li>)}</ul>
        </div>
      )}
      {!!payload.milestones?.length && (
        <div className="card__field">
          <h4>{w.milestones}</h4>
          <ul>
            {payload.milestones.map((m) => (
              <li key={m.title}>
                {m.title} <span className="muted">{m.due_date ? formatDate(m.due_date, w.locale) : w.noDate}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

/** The answer buttons of each kind (Why? and Not now are below the card). */
function Answers({ proposal, busy, answer, w }: { proposal: Proposal; busy: boolean; answer: (c: Click) => void; w: Words }) {
  const { kind, payload } = proposal;
  const reject = <button className="btn btn--soft" disabled={busy} onClick={() => answer({ action: "reject" })}><FontAwesomeIcon icon={faXmark} /> {w.reject}</button>;
  const take = <button className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "take" })}><FontAwesomeIcon icon={faHandshake} /> {w.take}</button>;
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
          <button className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "confirm" })}><FontAwesomeIcon icon={faCheck} /> {w.yesDepends}</button>
          <button className="btn btn--soft" disabled={busy} onClick={() => answer({ action: "reject" })}><FontAwesomeIcon icon={faXmark} /> {w.noDepends}</button>
        </>
      );
    }
    return (
      <>
        <button className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "confirm" })}><FontAwesomeIcon icon={faCheck} /> {w.markBlocked}</button>
        {reject}
      </>
    );
  }
  if (kind === "task_owner") {
    return (
      <>
        {payload.owner_id ? <button className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "confirm" })}><FontAwesomeIcon icon={faCheck} /> {w.confirm}</button> : null}
        {take}
        {reject}
      </>
    );
  }
  return (
    <>
      <button className="btn btn--primary" disabled={busy} onClick={() => answer({ action: "confirm" })}><FontAwesomeIcon icon={faCheck} /> {w.confirm}</button>
      {reject}
    </>
  );
}

/** The status under a card, with who answered it once someone did (the outcome is visible to everyone). */
function statusLine(proposal: Proposal, memberName: (id: MemberId) => string, w: Words): string {
  const who = proposal.resolved_by != null ? memberName(proposal.resolved_by) : null;
  if (who && proposal.status === "applied") return w.confirmedBy(who);
  if (who && proposal.status === "rejected") return w.turnedDownBy(who);
  if (who && proposal.status === "snoozed") return w.snoozedBy(who);
  return w.status[proposal.status] ?? proposal.status;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="card__field">
      <h4>{label}</h4>
      <p>{children}</p>
    </div>
  );
}

export function formatDate(iso: string, locale = "en-GB"): string {
  const date = new Date(`${iso}T12:00:00`);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString(locale, { day: "numeric", month: "short" });
}

/**
 * A card's reason and findings are Cadence's words, read like its chat replies:
 * "**30%**" in bold, never the asterisks (20/11 screenshot). Plain text only,
 * never HTML.
 */
function rich(text: string): ReactNode {
  return inline(text).map((p, n) => (p.bold ? <strong key={n}>{p.text}</strong> : <span key={n}>{p.text}</span>));
}
