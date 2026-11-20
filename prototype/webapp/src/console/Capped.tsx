import { useState, type ReactNode } from "react";
import { Dialog } from "./Dialogs";

/**
 * A list that never makes its page scroll: the first `limit` items in place,
 * the whole list in a popup ("See all N"). Pages and panels stay one screen
 * tall however much the group writes (20/11: members, Reflection, In words).
 */
export function Capped<T>({
  items,
  limit,
  title,
  render,
  className,
  label,
}: {
  items: T[];
  limit: number;
  /** The popup's title, e.g. "New tasks this week". */
  title: string;
  render: (item: T, index: number) => ReactNode;
  className?: string;
  /** The list's accessible name. */
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const shown = items.length > limit ? items.slice(0, limit) : items;
  return (
    <>
      <ul className={className} aria-label={label}>{shown.map(render)}</ul>
      {items.length > limit && (
        <button type="button" className="link-btn capped__more" onClick={() => setOpen(true)}>
          See all {items.length}
        </button>
      )}
      <Dialog open={open} title={title} onClose={() => setOpen(false)}>
        {/* Only while open: a closed popup must not hold a second copy of the list. */}
        {open && <ul className={`${className ?? ""} capped__all`}>{items.map(render)}</ul>}
        <div className="form__actions">
          <button type="button" className="btn btn--soft" onClick={() => setOpen(false)}>Close</button>
        </div>
      </Dialog>
    </>
  );
}
