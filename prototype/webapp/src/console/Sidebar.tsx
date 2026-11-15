import { useState } from "react";
import type { Space } from "./space";
import { dotFor } from "./space";

type Props = { space: Space; onProfile: () => void; onLeave: () => void };

export function Sidebar({ space, onProfile, onLeave }: Props) {
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
      <p className="brand">Cadence</p>
      <h1 className="side__group">{space.group?.name}</h1>

      <div className="side__block">
        <h2>Invite code</h2>
        <div className="invite">
          <code>{code}</code>
          <button className="btn btn--quiet btn--small" onClick={copy}>{copied ? "Copied" : "Copy"}</button>
        </div>
        <p className="muted small">Share it with your group. Anyone with the code can join.</p>
      </div>

      <div className="side__block">
        <h2>Members</h2>
        <ul className="members">
          {space.members.map((m) => (
            <li key={m.id}>
              <span className="dot" style={{ background: dotFor(m.id, space.members) }} aria-hidden="true" />
              {m.name}
              {m.id === space.me?.id && <span className="muted small"> (you)</span>}
            </li>
          ))}
        </ul>
      </div>

      <div className="side__foot">
        <button className="btn btn--quiet" onClick={onProfile}>Edit my profile</button>
        <button className="btn btn--link" onClick={onLeave}>Leave on this browser</button>
      </div>
    </nav>
  );
}
