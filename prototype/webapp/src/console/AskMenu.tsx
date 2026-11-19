import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import type { IconDefinition } from "@fortawesome/fontawesome-svg-core";
import { useEffect, useId, useRef, useState } from "react";
import { faChevronDown } from "../lib/icons";

export type AskItem = { key: string; label: string; about: string; icon: IconDefinition; run: () => void };

/**
 * "Ask Cadence": the on-demand actions (assignment, tasks, check-in, catch up)
 * behind one button, so the first screen has one thing to look at, the chat.
 * Cadence still steps in on its own; this menu is for when the group asks.
 *
 * Menu button pattern (WAI-ARIA APG): Enter/Space/ArrowDown open it on the
 * first item, arrows move, Escape closes and gives focus back to the button.
 * Each item's name is its visible text, label then one line of help
 * (axe label-content-name-mismatch), so it starts with the label.
 */
export function AskMenu({ items, label = "Ask Cadence" }: { items: AskItem[]; label?: string }) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();

  const entries = () => Array.from(list.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]") ?? []);

  useEffect(() => {
    if (!open) return;
    entries()[0]?.focus();
    const outside = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);

  const close = () => {
    setOpen(false);
    button.current?.focus();
  };

  const onKey = (e: React.KeyboardEvent) => {
    const all = entries();
    const at = all.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      all[(at + 1) % all.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      all[(at - 1 + all.length) % all.length]?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      all[0]?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      all[all.length - 1]?.focus();
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div className="ask" ref={root}>
      <button
        ref={button}
        className="btn btn--soft btn--small"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && !open) {
            e.preventDefault();
            setOpen(true);
          }
        }}
      >
        {label} <FontAwesomeIcon icon={faChevronDown} />
      </button>
      {open && (
        <ul id={id} ref={list} className="ask__menu" role="menu" aria-label={label} onKeyDown={onKey}>
          {items.map((item) => (
            <li key={item.key} role="none">
              <button
                role="menuitem"
                className="ask__item"
                tabIndex={-1}
                onClick={() => {
                  close();
                  item.run();
                }}
              >
                <FontAwesomeIcon icon={item.icon} className="ask__icon" />
                <span>
                  <span className="ask__label">{item.label}</span>
                  <span className="ask__about">{item.about}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
