import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState } from "react";
import { faCheck, faComments, faCopy, faDiagramProject, faFlag, faLightbulb, faListCheck, faPlus, faRightFromBracket, faTrashCan, faUserPen } from "../lib/icons";
import { copyText, inviteLink } from "../lib/invite";
import { AskMenu } from "./AskMenu";
import { initials } from "./Chat";
import type { Space } from "./space";
import { dotFor } from "./space";

export type NewWhat = "task" | "milestone";
/** The pages of the left rail. The chat is the first and the one a space opens on. */
export type View = "chat" | "dependencies" | "milestones" | "reflection";

const PAGES: { key: View; label: string; icon: typeof faComments }[] = [
  { key: "chat", label: "Chat", icon: faComments },
  { key: "dependencies", label: "Dependencies", icon: faDiagramProject },
  { key: "milestones", label: "Milestones", icon: faFlag },
  { key: "reflection", label: "Reflection", icon: faLightbulb },
];

type Props = { space: Space; view: View; onView: (view: View) => void; onProfile: () => void; onLeave: () => void; onDelete: () => void; onNew: (what: NewWhat) => void };

// A group is small, but the list must never push the rest of the sidebar away.
const MEMBERS_SHOWN = 6;

export function Sidebar({ space, view, onView, onProfile, onLeave, onDelete, onNew }: Props) {
  const [copied, setCopied] = useState(false);
  const [allMembers, setAllMembers] = useState(false);
  // You first, then the others as they joined.
  const ordered = [...space.members].sort((a, b) => Number(b.id === space.me?.id) - Number(a.id === space.me?.id));
  const members = allMembers ? ordered : ordered.slice(0, MEMBERS_SHOWN);
  const code = space.group?.inviteCode ?? "";

  // The link opens the login page with the code filled in: one click for a teammate.
  async function copy() {
    if (await copyText(inviteLink(code))) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <nav className="side" aria-label="Space">
      <p className="brand"><span className="brand__mark" aria-hidden="true" />Cadence</p>
      <h1 className="side__group">{space.group?.name}</h1>

      {/* New = what a member creates by hand, always in a popup. Ask Cadence (by the chat) asks the assistant. */}
      <div className="side__new">
        <AskMenu
          label="New"
          icon={faPlus}
          items={[
            { key: "task", label: "Task", about: "A name, an owner, a date, and what it waits on.", icon: faListCheck, run: () => onNew("task") },
            { key: "milestone", label: "Milestone", about: "A date the group works towards.", icon: faFlag, run: () => onNew("milestone") },
          ]}
        />
      </div>

      <ul className="side__pages" aria-label="Pages">
        {PAGES.map((page) => (
          <li key={page.key}>
            <button className="side__page" aria-current={view === page.key ? "page" : undefined} onClick={() => onView(page.key)}>
              <FontAwesomeIcon icon={page.icon} className="side__icon" /> {page.label}
            </button>
          </li>
        ))}
      </ul>

      <div className="side__block">
        <h2>Invite code</h2>
        <div className="invite">
          <code>{code}</code>
          <button className="btn btn--soft btn--small" onClick={copy}><FontAwesomeIcon icon={copied ? faCheck : faCopy} /> {copied ? "Copied" : "Copy link"}</button>
        </div>
        <p className="muted small">Send the link to your group: it opens Cadence with the code filled in. Anyone with the code can join.</p>
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
