import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useRef, useState } from "react";
import { faXmark } from "../lib/icons";

/** Long enough to read two lines; paused while the pointer or the focus is on it. */
const SHOW_MS = 7000;
const LONG = 140;

/**
 * Cadence's short answers to an action ("Task added", "Dependency saved"):
 * a toast over the page, never a banner that pushes the page down. Long text
 * shows two lines and "Read all"; it never grows past a third of the screen.
 * Rendered with key={text}, so a new message starts closed.
 */
export function Toast({ text, onClose }: { text: string; onClose: () => void }) {
  const [open, setOpen] = useState(false);
  const [held, setHeld] = useState(false);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    if (held || open) return;
    const timer = setTimeout(() => close.current(), SHOW_MS);
    return () => clearTimeout(timer);
  }, [text, held, open]);

  const long = text.length > LONG || text.includes("\n");
  return (
    <div
      className={`toast${open ? " toast--open" : ""}`}
      role="status"
      aria-live="polite"
      onPointerEnter={() => setHeld(true)}
      onPointerLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
    >
      <p className="toast__text">{text}</p>
      <div className="toast__actions">
        {long && (
          <button type="button" className="link-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? "Show less" : "Read all"}
          </button>
        )}
        <button type="button" className="icon-btn toast__close" aria-label="Dismiss" onClick={onClose}>
          <FontAwesomeIcon icon={faXmark} />
        </button>
      </div>
    </div>
  );
}
