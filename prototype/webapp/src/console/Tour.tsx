import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** One stop of the tour: the element it points at (data-tour="..."), and what to say. */
type Stop = { target: string; title: string; text: string; side: "right" | "left" | "above" };

export const STOPS: Stop[] = [
  {
    target: "composer",
    title: "Talk to your group here",
    text: "Write as usual. To ask Cadence something directly, start with @coordinator, for example “@coordinator why did we choose React?”. Type / to see the commands.",
    side: "above",
  },
  {
    target: "chat",
    title: "Cadence steps in on its own",
    text: "When it notices a gap (a task with no owner, someone waiting on someone else, a decision going in circles) it posts a violet card with its reasons. Nothing changes until one of you confirms.",
    side: "left",
  },
  {
    target: "rail",
    title: "Quick actions",
    text: "Create a task or a milestone, see what is due today, and edit your profile. Cadence reads the same plan.",
    side: "left",
  },
  {
    target: "pages",
    title: "The memory of the project",
    text: "Tasks, what waits on what, milestones and the decisions with their reasons. Reflection shows how the week went.",
    side: "right",
  },
  {
    target: "room",
    title: "Bring your team in",
    text: "Share the room code or the link. You can also connect a Slack or Discord channel: the plan and the cards stay the same everywhere.",
    side: "right",
  },
];

// Once per browser: the tour is about the app, not about one space.
const KEY = "cadence:tour";

/** Whether this browser already saw (or skipped) the tour. */
export function tourSeen(): boolean {
  try {
    return localStorage.getItem(KEY) === "done";
  } catch {
    return true; // no storage: do not show it at every visit
  }
}

function markSeen() {
  try {
    localStorage.setItem(KEY, "done");
  } catch {
    /* private mode */
  }
}

type Box = { top: number; left: number };
const CARD_W = 320;
const GAP = 14;

/** Where the card goes next to the target, kept inside the window. */
function place(rect: DOMRect, side: Stop["side"], height: number): Box {
  let top = rect.top;
  let left = side === "right" ? rect.right + GAP : rect.left - CARD_W - GAP;
  if (side === "above") {
    top = rect.top - height - GAP;
    left = rect.left + rect.width / 2 - CARD_W / 2;
  }
  if (side === "left" && rect.width > innerWidth / 2) left = rect.left + rect.width / 2 - CARD_W / 2; // a wide target: centre on it
  return {
    top: Math.max(12, Math.min(top, innerHeight - height - 12)),
    left: Math.max(12, Math.min(left, innerWidth - CARD_W - 12)),
  };
}

/**
 * A short guided tour of the console, five stops, shown the first time a
 * space opens in this browser (and again from the "Tour" quick action). It never blocks: the page
 * stays usable, Escape or "Skip" closes it.
 */
export function Tour({ onClose }: { onClose: () => void }) {
  const [at, setAt] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const stop = STOPS[at]!;

  const close = () => {
    markSeen();
    onClose();
  };

  // Highlight the target and put the card beside it; again when the window changes size.
  useLayoutEffect(() => {
    const target = document.querySelector<HTMLElement>(`[data-tour="${stop.target}"]`);
    target?.classList.add("tour-target");
    const update = () => {
      if (!target) return setBox({ top: innerHeight / 2 - 100, left: innerWidth / 2 - CARD_W / 2 });
      setBox(place(target.getBoundingClientRect(), stop.side, card.current?.offsetHeight ?? 180));
    };
    update();
    addEventListener("resize", update);
    return () => {
      target?.classList.remove("tour-target");
      removeEventListener("resize", update);
    };
  }, [stop]);

  useEffect(() => heading.current?.focus(), [at]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  });

  const last = at === STOPS.length - 1;
  return (
    <div
      ref={card}
      className="tour"
      role="dialog"
      aria-modal="false"
      aria-labelledby="tour-title"
      style={box ? { top: box.top, left: box.left, width: CARD_W } : { visibility: "hidden" }}
    >
      <p className="tour__count">{at + 1} of {STOPS.length}</p>
      <h2 id="tour-title" ref={heading} tabIndex={-1}>{stop.title}</h2>
      <p>{stop.text}</p>
      <div className="tour__actions">
        <button className="btn btn--link btn--small" onClick={close}>{last ? "Close" : "Skip tour"}</button>
        <span className="tour__dots" aria-hidden="true">{STOPS.map((s, i) => <i key={s.target} className={i === at ? "is-on" : undefined} />)}</span>
        {at > 0 && <button className="btn btn--soft btn--small" onClick={() => setAt(at - 1)}>Back</button>}
        <button className="btn btn--primary btn--small" onClick={() => (last ? close() : setAt(at + 1))}>{last ? "Start talking" : "Next"}</button>
      </div>
    </div>
  );
}
