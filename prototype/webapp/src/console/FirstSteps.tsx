import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState } from "react";
import { faUserPen, faXmark } from "../lib/icons";
import type { MemberId, ProjectState } from "../lib/types";

type Props = {
  state: ProjectState | null;
  me: MemberId | null;
  memberCount: number;
  inviteCode: string;
  onProfile: () => void;
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

/**
 * One short, skippable hint above the chat: who to bring in, and that the
 * profile is optional. Nothing here blocks the chat; the assignment and the
 * tasks are in "Ask Cadence" for when the group wants them (tutor, 18 Nov:
 * onboarding short and progressive; you start by talking, not by planning).
 *
 * Shown while you are alone in the space, or your profile is empty; gone
 * for good once dismissed in this browser tab.
 */
export function FirstSteps({ state, me, memberCount, inviteCode, onProfile }: Props) {
  const [hidden, setHidden] = useState(false);
  if (!state || hidden) return null; // not loaded yet: do not flash the hint
  const { profile } = firstSteps(state, me);
  const alone = memberCount <= 1;
  if (!alone && profile) return null;

  return (
    <section className="hint" aria-labelledby="hint-title">
      <div className="hint__text">
        <h3 id="hint-title">{alone ? "Bring your teammates in" : "Help Cadence suggest owners"}</h3>
        <p className="muted small">
          {alone
            ? `Send them the invite code${inviteCode ? ` ${inviteCode}` : ""} from the left, then just talk here.`
            : "Optional: your discipline, skills and free hours let Cadence suggest who could take a task."}
          {alone && !profile && " Adding your profile is optional."}
        </p>
      </div>
      <div className="hint__actions">
        {!profile && (
          <button className="btn btn--soft btn--small" onClick={onProfile}>
            <FontAwesomeIcon icon={faUserPen} /> Add my profile
          </button>
        )}
        <button className="btn btn--link btn--small" onClick={() => setHidden(true)} aria-label="Hide this hint">
          <FontAwesomeIcon icon={faXmark} />
        </button>
      </div>
    </section>
  );
}
