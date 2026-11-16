import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState } from "react";
import { faCheck } from "../lib/icons";
import { MILESTONES, PLACES, RETRO, SLOWER, TILES } from "./sample";

const days = (n: number) => `${n} day${n === 1 ? "" : "s"}`;

/**
 * The page a group gets when the project ends (reflection phase, CS10):
 * Cadence prepares the account from the plan and the log; the group judges it.
 */
export function Reflection() {
  const [kept, setKept] = useState<Set<string>>(new Set());
  const [saved, setSaved] = useState(false);
  const total = RETRO.reduce((n, c) => n + c.items.length, 0);

  function toggle(item: string) {
    const next = new Set(kept);
    if (!next.delete(item)) next.add(item);
    setKept(next);
    setSaved(false);
  }

  return (
    <>
      <header className="preview__head">
        <h1>How the project went.</h1>
        <p>
          When the last milestone closes, Cadence compares the plan with what happened and prepares this page from the decision log and the
          check-ins. The group reads it together and decides what to keep for next time.
        </p>
      </header>

      <ul className="tiles" aria-label="The project in four numbers">
        {TILES.map((t) => (
          <li key={t.label} className="panel-card">
            <p className="tiles__label">{t.label}</p>
            <p className="tiles__value">{t.value}</p>
            <p className="muted small">{t.note}</p>
          </li>
        ))}
      </ul>

      <div className="reflect">
        <section className="panel-card" aria-labelledby="pvr-title">
          <h2 id="pvr-title">Plan and reality</h2>
          <table className="table">
            <thead>
              <tr><th scope="col">Milestone</th><th scope="col">Planned</th><th scope="col">Done</th><th scope="col">Difference</th></tr>
            </thead>
            <tbody>
              {MILESTONES.map((m) => (
                <tr key={m.title}>
                  <th scope="row">{m.title}</th>
                  <td>{m.planned}</td>
                  <td>{m.actual}</td>
                  <td className={m.late ? "table__late" : "muted"}>{m.late ? `${days(m.late)} late` : "on time"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel-card" aria-labelledby="slow-title">
          <h2 id="slow-title">What took longer than planned</h2>
          <ul className="slower">
            {SLOWER.map((s) => (
              <li key={s.title}>
                <p><strong>{s.title}</strong> <span className="muted">planned {days(s.planned)}, took {days(s.took)}</span></p>
                <blockquote>
                  “{s.note}”
                  <cite>{s.who}</cite>
                </blockquote>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel-card" aria-labelledby="places-title">
          <h2 id="places-title">Where the group talked</h2>
          <ul className="bars">
            {PLACES.map((p) => (
              <li key={p.name}>
                <span className="bars__name">{p.name}</span>
                <span className="bars__track" aria-hidden="true"><i style={{ width: `${p.share}%` }} /></span>
                <span className="bars__value">{p.share} %</span>
              </li>
            ))}
          </ul>
          <p className="muted small">Share of the group's messages. Four of the seven decisions were taken in a call; three reached a member who was absent through a catch-up.</p>
        </section>
      </div>

      <section className="preview__section" aria-labelledby="retro-title">
        <h2 id="retro-title">For next time</h2>
        <p className="muted">Cadence prepared these points from the log. Keep the ones the group agrees with.</p>
        <div className="retro">
          {RETRO.map((c) => (
            <div key={c.column} className="panel-card">
              <h3>{c.column}</h3>
              <ul>
                {c.items.map((item) => (
                  <li key={item}>
                    <button className="keep" aria-pressed={kept.has(item)} onClick={() => toggle(item)}>
                      <span className="keep__box" aria-hidden="true">{kept.has(item) && <FontAwesomeIcon icon={faCheck} />}</span>
                      {item}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <div className="retro__foot">
          <p role="status">{saved ? `Saved: ${kept.size} of ${total} points kept, confirmed by Ada.` : `${kept.size} of ${total} points kept. Nothing is saved until a member confirms.`}</p>
          <button className="btn btn--primary" disabled={saved || kept.size === 0} onClick={() => setSaved(true)}><FontAwesomeIcon icon={faCheck} /> Save the reflection</button>
        </div>
      </section>
    </>
  );
}
