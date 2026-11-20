import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState } from "react";
import { faBookmark, faCheck, faComments, faCopy, faDiagramProject, faFlag, faGear, faLightbulb, faListCheck, faPlug, faRightFromBracket } from "../lib/icons";
import type { MemberId } from "../lib/types";
import { copyText, inviteLink } from "../lib/invite";
import { LogoMark } from "../brand/Logo";
import { initials } from "./Chat";
import { Dialog } from "./Dialogs";
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

type Props = { space: Space; view: View; onView: (view: View) => void; onLeave: () => void; onSettings: () => void; onMember: (id: MemberId) => void; onConnect: () => void; /** Quick access is a sheet over the page: nothing behind it can be reached. */ inert?: boolean };

// The rail shows a few members; the whole team (with a search) opens in a popup,
// so a big group never pushes the pages and the room code out of sight.
const MEMBERS_SHOWN = 3;

export function Sidebar({ space, view, onView, onLeave, onSettings, onMember, onConnect, inert }: Props) {
  const [copied, setCopied] = useState(false);
  const [allMembers, setAllMembers] = useState(false);
  const [find, setFind] = useState("");
  // You first, then the others as they joined.
  const ordered = [...space.members].sort((a, b) => Number(b.id === space.me?.id) - Number(a.id === space.me?.id));
  const members = ordered.slice(0, MEMBERS_SHOWN);
  const found = ordered.filter((m) => m.name.toLowerCase().includes(find.trim().toLowerCase()));
  const row = (m: (typeof ordered)[number], onPick: () => void) => (
    <li key={m.id}>
      {/* A teammate's profile opens in a popup. */}
      <button className="members__row" onClick={onPick}>
        <span className="avatar avatar--small" style={{ background: dotFor(m.id, space.members) }} aria-hidden="true">{initials(m.name)}</span>
        <span className="members__name">
          {m.name}
          {m.id === space.me?.id && <span className="muted small"> (you)</span>}
        </span>
      </button>
    </li>
  );
  const code = space.group?.inviteCode ?? "";

  // The link opens the login page with the code filled in: one click for a teammate.
  async function copy() {
    if (await copyText(inviteLink(code))) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <nav className="side" aria-label="Space" inert={inert}>
      <p className="brand"><LogoMark size={22} />Cadence</p>
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
        <ul className="members">{members.map((m) => row(m, () => onMember(m.id)))}</ul>
        {space.members.length > MEMBERS_SHOWN && (
          <button className="members__more" onClick={() => { setFind(""); setAllMembers(true); }}>
            <span className="members__stack" aria-hidden="true">
              {ordered.slice(MEMBERS_SHOWN, MEMBERS_SHOWN + 3).map((m) => (
                <span key={m.id} className="avatar avatar--tiny" style={{ background: dotFor(m.id, space.members) }}>{initials(m.name)}</span>
              ))}
            </span>
            See all {space.members.length}
          </button>
        )}
      </div>

      {/* The room: the code to invite the team, and the way to the other channels. */}
      <div className="room" data-tour="room">
        <h2 id="room-code">Room code</h2>
        <div className="invite" aria-labelledby="room-code">
          <code title="Send the link to your group: it opens Cadence with the code filled in.">{code}</code>
          <button className="btn btn--soft btn--small invite__copy" onClick={copy} aria-label={copied ? "Copied" : "Copy link"} title="Copy the invite link: it opens Cadence with the code filled in">
            <FontAwesomeIcon icon={copied ? faCheck : faCopy} /> <span className="invite__label">{copied ? "Copied" : "Copy link"}</span>
          </button>
        </div>
        <button className="link-btn room__connect" onClick={onConnect}><FontAwesomeIcon icon={faPlug} /> Connect Slack or Discord</button>
      </div>

      <Dialog open={allMembers} title={`Members (${space.members.length})`} onClose={() => setAllMembers(false)}>
        {space.members.length > 6 && (
          <input className="members__find" type="search" placeholder="Find a member" aria-label="Find a member" value={find} onChange={(e) => setFind(e.target.value)} />
        )}
        {allMembers && (
          <ul className="members members--all">
            {found.map((m) => row(m, () => { setAllMembers(false); onMember(m.id); }))}
            {found.length === 0 && <li className="muted small">Nobody with that name.</li>}
          </ul>
        )}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={() => setAllMembers(false)}>Close</button>
        </div>
      </Dialog>

      <div className="side__foot">
        <button className="btn btn--link" onClick={onLeave}><FontAwesomeIcon icon={faRightFromBracket} /> Back to my spaces</button>
      </div>
    </nav>
  );
}
