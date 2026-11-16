import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import { useState } from "react";
import { faCalendarDays, faCodeBranch, faComments, faCompass, faFolderOpen, faHashtag, faLink, faLock } from "../lib/icons";
import { CHANNELS, SOURCES, type Connection } from "./sample";

const ICONS: Record<string, IconDefinition> = {
  web: faCompass,
  discord: faHashtag,
  slack: faComments,
  calendar: faCalendarDays,
  drive: faFolderOpen,
  github: faCodeBranch,
};

/** Where the group talks and what Cadence may read: one plan and one memory behind all of it. */
export function Connections() {
  const [on, setOn] = useState<Record<string, boolean>>(() =>
    Object.fromEntries([...CHANNELS, ...SOURCES].map((c) => [c.id, c.connected])),
  );
  const toggle = (id: string) => setOn((now) => ({ ...now, [id]: !now[id] }));

  return (
    <>
      <header className="preview__head">
        <h1>Keep talking where you already are.</h1>
        <p>
          Cadence keeps one plan and one memory for the group. Link the places you already use: it reads along there, answers there,
          and what you decide in one place is known in all of them.
        </p>
      </header>
      <Group title="Channels" lead="Where Cadence listens and writes its cards." items={CHANNELS} on={on} toggle={toggle} />
      <Group title="Sources" lead="What Cadence may read to make better proposals. It never writes to them." items={SOURCES} on={on} toggle={toggle} />
      <p className="preview__note">
        <FontAwesomeIcon icon={faLock} /> A private message to Cadence can read the group's plan and decisions, but it is never added to the
        group's memory.
      </p>
    </>
  );
}

function Group({ title, lead, items, on, toggle }: { title: string; lead: string; items: Connection[]; on: Record<string, boolean>; toggle: (id: string) => void }) {
  return (
    <section className="preview__section" aria-labelledby={`conn-${title}`}>
      <h2 id={`conn-${title}`}>{title}</h2>
      <p className="muted">{lead}</p>
      <ul className="conn">
        {items.map((c) => (
          <li key={c.id} className="panel-card">
            <span className="bento__icon"><FontAwesomeIcon icon={ICONS[c.id] ?? faLink} /></span>
            <div className="conn__text">
              <h3>
                {c.name}
                <span className={`tag${on[c.id] ? " tag--on" : ""}`}>{c.fixed ? "Always on" : on[c.id] ? "Connected" : "Not connected"}</span>
              </h3>
              <p>{c.detail}</p>
              <p className="muted small">Reads: {c.reads}</p>
            </div>
            {!c.fixed && (
              <button className={`btn btn--small ${on[c.id] ? "btn--soft" : "btn--primary"}`} aria-label={`${on[c.id] ? "Disconnect" : "Connect"} ${c.name}`} onClick={() => toggle(c.id)}>
                {on[c.id] ? "Disconnect" : "Connect"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
