import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState } from "react";
import { faBookmark, faCheck, faComments, faCopy, faDiagramProject, faFlag, faGear, faLightbulb, faListCheck, faPlug, faRightFromBracket } from "../lib/icons";
import type { MemberId } from "../lib/types";
import { copyText, inviteLink } from "../lib/invite";
import { initials } from "./Chat";
import type { Space } from "./space";
import { dotFor } from "./space";

export type NewWhat = "task" | "milestone";
/** The pages of the left rail. The chat is the first and the one a space opens on. */
export type View = "chat" | "tasks" | "dependencies" | "milestones" | "decisions" | "reflection";

const PAGES: { key: View; label: string; icon: typeof faComments }[] = [
  { key: "chat", label: "Chat", icon: faComments },
  { key: "tasks", label: "Tasks", icon: faListCheck },
  { key: "dependencies", label: "Dependencies", icon: faDiagramProject },
  { key: "milestones", label: "Milestones", icon: faFlag },
  { key: "decisions", label: "Decisions", icon: faBookmark },
  { key: "reflection", label: "Reflection", icon: faLightbulb },
];

type Props = { space: Space; view: View; onView: (view: View) => void; onLeave: () => void; onSettings: () => void; onMember: (id: MemberId) => void; onConnect: () => void };

// A group is small, but the list must never push the rest of the sidebar away.
const MEMBERS_SHOWN = 6;

export function Sidebar({ space, view, onView, onLeave, onSettings, onMember, onConnect }: Props) {
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
      <div className="side__head">
        <h1 className="side__group">{space.group?.name}</h1>
        <button className="icon-btn side__gear" aria-label="Project settings" title="Project settings" onClick={onSettings}>
          <FontAwesomeIcon icon={faGear} />
        </button>
      </div>

      <ul className="side__pages" aria-label="Pages" data-tour="pages">
        {PAGES.map((page) => (
          <li key={page.key}>
            <button className="side__page" aria-current={view === page.key ? "page" : undefined} onClick={() => onView(page.key)}>
              <FontAwesomeIcon icon={page.icon} className="side__icon" /> {page.label}
            </button>
          </li>
        ))}
      </ul>

      <div className="side__block">
        <h2>Members ({space.members.length})</h2>
        <ul className="members">
          {members.map((m) => (
            <li key={m.id}>
              {/* A teammate's profile opens in a popup. */}
              <button className="members__row" onClick={() => onMember(m.id)}>
                <span className="avatar avatar--small" style={{ background: dotFor(m.id, space.members) }} aria-hidden="true">{initials(m.name)}</span>
                <span className="members__name">
                  {m.name}
                  {m.id === space.me?.id && <span className="muted small"> (you)</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
        {space.members.length > MEMBERS_SHOWN && (
          <button className="link-btn" onClick={() => setAllMembers(!allMembers)}>{allMembers ? "Show fewer" : `Show all ${space.members.length}`}</button>
        )}
      </div>

      {/* The room: the code to invite the team, and the way to the other channels. */}
      <div className="room" data-tour="room">
        <h2>Room code</h2>
        <div className="invite">
          <code>{code}</code>
          <button className="btn btn--soft btn--small" onClick={copy}><FontAwesomeIcon icon={copied ? faCheck : faCopy} /> {copied ? "Copied" : "Copy link"}</button>
        </div>
        <p className="muted small">Send the link to your group: it opens Cadence with the code filled in.</p>
        <button className="link-btn room__connect" onClick={onConnect}><FontAwesomeIcon icon={faPlug} /> Connect Slack or Discord</button>
      </div>

      <div className="side__foot">
        <button className="btn btn--link" onClick={onLeave}><FontAwesomeIcon icon={faRightFromBracket} /> Back to my spaces</button>
      </div>
    </nav>
  );
}
