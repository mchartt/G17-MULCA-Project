import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState } from "react";
import { faCheck, faCopy, faRightFromBracket, faTrashCan, faUserPen } from "../lib/icons";
import { initials } from "./Chat";
import type { Space } from "./space";
import { dotFor } from "./space";

type Props = { space: Space; onProfile: () => void; onLeave: () => void; onDelete: () => void };

// A group is small, but the list must never push the rest of the sidebar away.
const MEMBERS_SHOWN = 6;

export function Sidebar({ space, onProfile, onLeave, onDelete }: Props) {
  const [copied, setCopied] = useState(false);
  const [allMembers, setAllMembers] = useState(false);
  // You first, then the others as they joined.
  const ordered = [...space.members].sort((a, b) => Number(b.id === space.me?.id) - Number(a.id === space.me?.id));
  const members = allMembers ? ordered : ordered.slice(0, MEMBERS_SHOWN);
  const code = space.group?.inviteCode ?? "";

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* the code stays visible to copy by hand */
    }
  }

  return (
    <nav className="side" aria-label="Space">
      <p className="brand"><span className="brand__mark" aria-hidden="true" />Cadence</p>
      <h1 className="side__group">{space.group?.name}</h1>

      <div className="side__block">
        <h2>Invite code</h2>
        <div className="invite">
          <code>{code}</code>
          <button className="btn btn--soft btn--small" onClick={copy}><FontAwesomeIcon icon={copied ? faCheck : faCopy} /> {copied ? "Copied" : "Copy"}</button>
        </div>
        <p className="muted small">Share it with your group. Anyone with the code can join.</p>
      </div>

      <details className="side__block side__more">
        <summary>Use it from Discord or Slack</summary>
        <p className="muted small">Where the Cadence bot is installed in your group's server or workspace, write this in the channel:</p>
        <code className="side__command">/coordinator link {code}</code>
        <p className="muted small">The plan, the decisions and the cards are then the same everywhere, and messages show in both places. Without the bot the command does nothing.</p>
      </details>

      <div className="side__block">
        <h2>Members ({space.members.length})</h2>
        <ul className="members">
          {members.map((m) => (
            <li key={m.id}>
              <span className="avatar avatar--small" style={{ background: dotFor(m.id, space.members) }} aria-hidden="true">{initials(m.name)}</span>
              {m.name}
              {m.id === space.me?.id && <span className="muted small"> (you)</span>}
            </li>
          ))}
        </ul>
        {space.members.length > MEMBERS_SHOWN && (
          <button className="link-btn" onClick={() => setAllMembers(!allMembers)}>{allMembers ? "Show fewer" : `Show all ${space.members.length}`}</button>
        )}
      </div>

      <div className="side__foot">
        <button className="btn btn--soft" onClick={onProfile}><FontAwesomeIcon icon={faUserPen} /> Edit my profile</button>
        <button className="btn btn--link" onClick={onLeave}><FontAwesomeIcon icon={faRightFromBracket} /> Back to my spaces</button>
      </div>

      <details className="side__more side__settings">
        <summary>Space settings</summary>
        <button className="btn btn--link btn--danger" onClick={onDelete}><FontAwesomeIcon icon={faTrashCan} /> Delete this space</button>
      </details>
    </nav>
  );
}
