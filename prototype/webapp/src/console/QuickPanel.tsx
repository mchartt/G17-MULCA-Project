import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark } from "../lib/icons";
import { todayIso, todayView, type Task } from "./plan";

/** One thing the panel does: a visible name, one line saying what it does, and its icon. */
export type QuickEntry = { key: string; label: string; about: string; icon: IconDefinition; run: () => void; badge?: number };
/** Entries that belong together. "cadence" tints the icons violet: Cadence does the work there. */
export type QuickGroup = { key: string; title: string; note?: string; tone?: "cadence"; entries: QuickEntry[] };

/** What is due today, in the words the Today popup uses, and how many things that is. */
export function todaySummary(tasks: Task[]): { about: string; count: number } {
  const view = todayView(tasks, todayIso());
  const count = view.late.length + view.today.length;
  if (count === 0) return { about: "Nothing due today.", count };
  const parts = [view.today.length > 0 && `${view.today.length} due`, view.late.length > 0 && `${view.late.length} late`].filter(Boolean);
  return { about: `${parts.join(", ")}. Open it to tick them off.`, count };
}

export const capBadge = (count: number) => (count > 99 ? "99+" : String(count));

/**
 * Quick access, always on the right: everything a member can ask Cadence for,
 * their dates, and their own profile, each button with one line saying what
 * it does. The plan itself lives on the left-hand pages; this panel only holds
 * the shortcuts that work from any of them, so nothing here repeats a page.
 *
 * A button's name is its visible text (label, then its line of help), so a
 * screen reader hears what a sighted member reads (axe label-content-name-mismatch).
 */
export function QuickPanel({ groups, onClose }: { groups: QuickGroup[]; onClose: () => void }) {
  return (
    <aside id="quick" className="quick" aria-labelledby="quick-title" data-tour="rail" onKeyDown={(e) => e.key === "Escape" && onClose()}>
      <div className="quick__head">
        <div>
          <h2 id="quick-title">Quick access</h2>
          <p>Shortcuts that work from every page.</p>
        </div>
        <button className="icon-btn quick__close" aria-label="Close quick access" title="Close quick access" onClick={onClose}><FontAwesomeIcon icon={faXmark} /></button>
      </div>
      {groups.map((group) => (
        <section key={group.key} className={`quick__group${group.tone ? ` quick__group--${group.tone}` : ""}`} aria-labelledby={`quick-${group.key}`}>
          <h3 id={`quick-${group.key}`}>{group.title}</h3>
          {group.note && <p className="quick__note">{group.note}</p>}
          <ul className="quick__list">
            {group.entries.map((entry) => (
              <li key={entry.key}>
                <button className="quick__item" onClick={entry.run}>
                  <span className="quick__icon" aria-hidden="true"><FontAwesomeIcon icon={entry.icon} /></span>
                  <span className="quick__text">
                    <span className="quick__label">{entry.label}</span>
                    <span className="quick__about">{entry.about}</span>
                  </span>
                  {!!entry.badge && <b className="quick__badge" aria-hidden="true">{capBadge(entry.badge)}</b>}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </aside>
  );
}
