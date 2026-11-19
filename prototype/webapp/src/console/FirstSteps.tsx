import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useState } from "react";
import { copyText, inviteLink } from "../lib/invite";
import { faCheck, faCopy, faFileLines, faLink, faUserPen } from "../lib/icons";
import type { MemberId, ProjectState } from "../lib/types";

/** The four setup steps, in Francesco's order (Figma, "Onboarding and setup"). */
export type StepKey = "team" | "profile" | "brief" | "charter";
const STEPS: { key: StepKey; label: string }[] = [
  { key: "team", label: "Team" },
  { key: "profile", label: "Profile" },
  { key: "brief", label: "Brief" },
  { key: "charter", label: "Charter" },
];

type Props = {
  state: ProjectState | null;
  me: MemberId | null;
  memberCount: number;
  inviteCode: string;
  /** The charter card waiting in the chat, if Cadence has proposed one. */
  charterCard: string | null;
  onProfile: () => void;
  onBrief: () => void;
};

/** Which first steps are done, read from the saved project state. */
export function firstSteps(state: ProjectState | null, me: MemberId | null): { profile: boolean; charter: boolean; plan: boolean } {
  const mine = state?.members?.find((m) => me !== null && String(m.member_id) === String(me));
  return {
    profile: !!mine && (!!mine.discipline?.trim() || (mine.skills?.length ?? 0) > 0),
    charter: !!state?.charter,
    plan: (state?.tasks?.length ?? 0) > 0,
  };
}

/** Skipped steps and the collapsed state, kept per space in this browser. */
type Saved = { skipped: StepKey[]; hidden: boolean };
const keyFor = (code: string) => `cadence:setup:${code}`;

function load(code: string): Saved {
  try {
    const raw = code ? localStorage.getItem(keyFor(code)) : null;
    return raw ? { skipped: [], hidden: false, ...JSON.parse(raw) } : { skipped: [], hidden: false };
  } catch {
    return { skipped: [], hidden: false };
  }
}

/**
 * Setting up a space, as four short steps above the chat: bring the team in,
 * add your profile, paste the brief, confirm the charter. It guides without
 * blocking (tutor, 18 Nov: a guided but short onboarding; you can always
 * just talk): every step can be skipped, the card folds to one line, and it
 * disappears once the charter is confirmed. Team and profile are optional;
 * the brief and the charter are what the coordinator needs to help.
 */
export function FirstSteps({ state, me, memberCount, inviteCode, charterCard, onProfile, onBrief }: Props) {
  const [saved, setSaved] = useState<Saved>(() => load(inviteCode));
  const [picked, setPicked] = useState<StepKey | null>(null);

  // The invite code arrives after the first render: read what this browser kept for it.
  useEffect(() => setSaved(load(inviteCode)), [inviteCode]);

  if (!state) return null; // not loaded yet: do not flash the card

  const save = (next: Saved) => {
    setSaved(next);
    try {
      if (inviteCode) localStorage.setItem(keyFor(inviteCode), JSON.stringify(next));
    } catch {
      /* private mode: the choice lasts until the page is reloaded */
    }
  };

  const steps = firstSteps(state, me);
  const done: Record<StepKey, boolean> = {
    team: memberCount > 1 || saved.skipped.includes("team"),
    profile: steps.profile || saved.skipped.includes("profile"),
    brief: steps.charter || charterCard !== null,
    charter: steps.charter,
  };
  if (done.charter) return null; // set up: the chat is the whole screen again

  const next = STEPS.find((s) => !done[s.key])?.key ?? "charter";
  const shown = picked ?? next;
  const skip = (key: StepKey) => {
    setPicked(null);
    save({ ...saved, skipped: [...saved.skipped, key] });
  };

  return (
    <section className="setup" aria-labelledby="setup-title">
      <div className="setup__head">
        <h3 id="setup-title">Set up your space</h3>
        <ol className="setup__steps">
          {STEPS.map((s, i) => (
            <li key={s.key}>
              <button
                className={`setup__step${done[s.key] ? " setup__step--done" : ""}`}
                aria-current={!saved.hidden && shown === s.key ? "step" : undefined}
                onClick={() => {
                  setPicked(s.key);
                  if (saved.hidden) save({ ...saved, hidden: false });
                }}
              >
                <span className="setup__dot" aria-hidden="true">{done[s.key] && <FontAwesomeIcon icon={faCheck} />}</span>
                {s.label}
                <span className="sr-only">{done[s.key] ? " (done)" : ` (step ${i + 1} of 4)`}</span>
              </button>
            </li>
          ))}
        </ol>
        <button className="btn btn--link btn--small" aria-expanded={!saved.hidden} onClick={() => save({ ...saved, hidden: !saved.hidden })}>
          {saved.hidden ? "Show" : "Hide"}
        </button>
      </div>

      {!saved.hidden && (
        <div className="setup__card">
          <p className="setup__count">Step {STEPS.findIndex((s) => s.key === shown) + 1} of 4</p>
          {shown === "team" && <TeamStep code={inviteCode} alone={memberCount <= 1} onSkip={() => skip("team")} />}
          {shown === "profile" && (
            <>
              <h4>Your profile</h4>
              <p>Your discipline, skills and free hours let Cadence suggest who could take a task. No scores, no rankings.</p>
              <div className="setup__actions">
                <button className="btn btn--primary btn--small" onClick={onProfile}><FontAwesomeIcon icon={faUserPen} /> Add my profile</button>
                {!done.profile && <button className="btn btn--link btn--small" onClick={() => skip("profile")}>Skip for now</button>}
              </div>
            </>
          )}
          {shown === "brief" && (
            <>
              <h4>Paste the brief</h4>
              <button className="setup__drop" onClick={onBrief}>
                <FontAwesomeIcon icon={faFileLines} />
                <strong>Paste the brief or upload the file</strong>
                <span className="muted small">Text or PDF, as your teacher gave it</span>
              </button>
              <p className="muted small">Cadence turns it into a goal, deliverables and milestones for the group to confirm. Nothing changes until a member does.</p>
            </>
          )}
          {shown === "charter" && <CharterStep card={charterCard} onBrief={onBrief} />}
        </div>
      )}
    </section>
  );
}

/** Step 1: the invite link (the code filled in) and the code itself, for Discord or by voice. */
function TeamStep({ code, alone, onSkip }: { code: string; alone: boolean; onSkip: () => void }) {
  const [copied, setCopied] = useState<"link" | "code" | null>(null);
  // When the browser refuses the clipboard, the link is shown to copy by hand.
  const [failed, setFailed] = useState(false);
  const copy = async (what: "link" | "code") => {
    const ok = await copyText(what === "link" ? inviteLink(code) : code);
    setFailed(!ok);
    if (ok) {
      setCopied(what);
      setTimeout(() => setCopied(null), 2000);
    }
  };
  return (
    <>
      <h4>{alone ? "Bring your team in" : "Invite the rest of the team"}</h4>
      <p>Send the link to your group chat. It opens Cadence with the code already filled in.</p>
      <p className="setup__code" role="img" aria-label={`Invite code ${code}`}>
        {code.split("").map((c, i) => <span key={i} aria-hidden="true">{c}</span>)}
      </p>
      <div className="setup__actions">
        <button className="btn btn--primary btn--small" onClick={() => void copy("link")}>
          <FontAwesomeIcon icon={copied === "link" ? faCheck : faLink} /> {copied === "link" ? "Link copied" : "Copy invite link"}
        </button>
        <button className="btn btn--soft btn--small" onClick={() => void copy("code")}>
          <FontAwesomeIcon icon={copied === "code" ? faCheck : faCopy} /> {copied === "code" ? "Copied" : "Copy code"}
        </button>
        {alone && <button className="btn btn--link btn--small" onClick={onSkip}>I'll do it later</button>}
      </div>
      <p className="muted small" role="status">
        {copied === "link" && "The invite link is copied."}
        {copied === "code" && "The invite code is copied."}
        {failed && <>Your browser did not allow copying. The link is <code>{inviteLink(code)}</code></>}
      </p>
    </>
  );
}

/** Step 4: the charter is a card in the chat; the group confirms it there, like every card. */
function CharterStep({ card, onBrief }: { card: string | null; onBrief: () => void }) {
  const show = () => {
    const title = card ? document.getElementById(`card-${card}`) : null;
    title?.closest("article")?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  return (
    <>
      <h4>Confirm the charter</h4>
      {card ? (
        <>
          <p>Cadence proposed the goal and the deliverables as a card in the chat. Read it with your group, then confirm it or edit it.</p>
          <div className="setup__actions">
            <button className="btn btn--primary btn--small" onClick={show}>Show the card</button>
          </div>
        </>
      ) : (
        <>
          <p>There is no charter card waiting. Paste the brief again and Cadence will propose one.</p>
          <div className="setup__actions">
            <button className="btn btn--soft btn--small" onClick={onBrief}>Paste the brief</button>
          </div>
        </>
      )}
    </>
  );
}
