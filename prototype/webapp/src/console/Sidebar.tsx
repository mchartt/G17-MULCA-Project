import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState } from "react";
import { faArrowRight, faCheck, faCopy, faRightFromBracket, faTrashCan, faUserPen } from "../lib/icons";
import { initials } from "./Chat";
import type { Space } from "./space";
import { dotFor } from "./space";

type Props = { space: Space; onProfile: () => void; onLeave: () => void; onDelete: () => void };

export function Sidebar({ space, onProfile, onLeave, onDelete }: Props) {
  const [copied, setCopied] = useState(false);
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

      <div className="side__block">
        <h2>Discord and Slack</h2>
        <p className="muted small">
          To share this project with your group's channel, write there:
        </p>
        <code className="side__command">/coordinator link {code}</code>
        <p className="muted small">The plan, the decisions and the cards are then the same everywhere, and messages show in both places.</p>
      </div>

      <div className="side__block">
        <h2>Members</h2>
        <ul className="members">
          {space.members.map((m) => (
            <li key={m.id}>
              <span className="avatar avatar--small" style={{ background: dotFor(m.id, space.members) }} aria-hidden="true">{initials(m.name)}</span>
              {m.name}
              {m.id === space.me?.id && <span className="muted small"> (you)</span>}
            </li>
          ))}
        </ul>
      </div>

      <div className="side__foot">
        <a className="btn btn--link" href="/preview"><FontAwesomeIcon icon={faArrowRight} /> What's next (preview)</a>
        <button className="btn btn--soft" onClick={onProfile}><FontAwesomeIcon icon={faUserPen} /> Edit my profile</button>
        <button className="btn btn--link" onClick={onLeave}><FontAwesomeIcon icon={faRightFromBracket} /> Back to my spaces</button>
        <button className="btn btn--link btn--danger" onClick={onDelete}><FontAwesomeIcon icon={faTrashCan} /> Delete this space</button>
      </div>
    </nav>
  );
}
