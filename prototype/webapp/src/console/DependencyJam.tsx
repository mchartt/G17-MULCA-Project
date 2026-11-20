// Dependencies as a jam board (Matteo, 20/11): every task is a sticky note,
// arrows show what waits on what, and Cadence's suggestions (CS7 "possible"
// cards, made when a task is added) are dashed arrows with Confirm / Not now.
// Notes start from an automatic layout (needed tasks left, the ones that wait
// on them right) and can be dragged; positions are kept in this browser only.
// The board is for looking; the list below says the same in words, for the
// keyboard and for screen readers.
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { faCheck, faCircleCheck, faLink, faMinus, faPlus, faUpRightAndDownLeftFromCenter } from "../lib/icons";
import type { MemberId, Proposal } from "../lib/types";
import { Capped } from "./Capped";
import { layoutDependencies } from "./graph";
import { finishedLongAgo, waitingOn, type Task } from "./plan";
import { useNow } from "./useNow";

const NOTE_W = 184;
const NOTE_H = 112;
const COL = 260;
const ROW = 148;
const PAD = 40;
const PORT = 18; // diameter of the dots on the notes
const STORE = "cadence.jam";

type Point = { x: number; y: number };
type Suggestion = { proposalId: string; from: string; to: string; question: string };

const STATUS_NAMES: Record<string, string> = { todo: "To do", doing: "In progress", done: "Done", blocked: "Blocked" };

function savedPositions(): Record<string, Point> {
  try {
    return JSON.parse(localStorage.getItem(STORE) ?? "{}");
  } catch {
    return {};
  }
}

function keepPositions(positions: Record<string, Point>) {
  try {
    localStorage.setItem(STORE, JSON.stringify(positions));
  } catch {
    /* private mode: the layout is recomputed next time */
  }
}

/** Where each note starts: linked tasks by layer, the others in a block below. */
export function startPositions(tasks: Task[], ideas: { from: string; to: string }[] = []): Record<string, Point> {
  // Cadence's suggested links count for the layout too, so a suggested pair sits side by side.
  const withIdeas = tasks.map((t) => {
    const extra = ideas.filter((i) => i.to === t.task_id).map((i) => i.from);
    return extra.length ? { ...t, depends_on: [...new Set([...(t.depends_on ?? []), ...extra])] } : t;
  });
  const { nodes, rows } = layoutDependencies(withIdeas);
  const out: Record<string, Point> = {};
  for (const n of nodes) out[n.id] = { x: PAD + n.layer * COL, y: PAD + n.row * ROW };
  const rest = tasks.filter((t) => t.task_id && !out[t.task_id]);
  const top = PAD + (nodes.length ? rows * ROW + 40 : 0);
  rest.forEach((t, i) => {
    out[t.task_id!] = { x: PAD + (i % 4) * (NOTE_W + 32), y: top + Math.floor(i / 4) * ROW };
  });
  return out;
}

/** The pending "possible dependency" cards, as arrows to draw. */
function suggestions(proposals: Proposal[]): Suggestion[] {
  return proposals.flatMap((p) => {
    const payload = p.payload as Record<string, unknown>;
    if (p.kind !== "blocker" || p.status !== "pending" || payload.certainty !== "possible") return [];
    const to = payload.task_id as string | undefined;
    const from = payload.depends_on_task_id as string | undefined;
    return to && from ? [{ proposalId: p.proposal_id, from, to, question: String(payload.question ?? "") }] : [];
  });
}

type Props = {
  tasks: Task[];
  proposals: Proposal[];
  nameOf: (id?: MemberId | null) => string | undefined;
  onNew: () => void;
  onLink: (taskId: string | null) => void;
  /** Drawn on the board: `to` now waits on `from` too. */
  onConnect?: (from: string, to: string) => void;
  /** Pulled off the board: `to` no longer waits on `from`. */
  onDisconnect?: (from: string, to: string) => void;
  onAnswer: (proposalId: string, action: "confirm" | "not_now") => void;
};

export function DependenciesPage({ tasks: allTasks, proposals, nameOf, onNew, onLink, onConnect, onDisconnect, onAnswer }: Props) {
  // A task finished more than an hour ago leaves the board and the list (Matteo, 20/11); a switch shows them again.
  const now = useNow();
  const [showFinished, setShowFinished] = useState(false);
  const finished = allTasks.filter((t) => t.task_id && finishedLongAgo(t, now));
  const tasks = showFinished ? allTasks : allTasks.filter((t) => !finished.includes(t));
  const withIds = tasks.filter((t) => t.task_id);
  const ideas = suggestions(proposals).filter((s) => withIds.some((t) => t.task_id === s.from) && withIds.some((t) => t.task_id === s.to));
  const rows = waitingOn(tasks);
  const titles = new Map(withIds.map((t) => [t.task_id!, t.title]));

  return (
    <section className="page jam-page" aria-label="Dependencies">
      <header className="page__head">
        <p className="muted">When a task needs another one finished first, it waits on it. Drag a note to move it; drag its dot onto another note to link them; click an arrow to change it.</p>
        <div className="page__actions">
          {withIds.length > 1 && <button className="btn btn--soft btn--small" onClick={() => onLink(null)}><FontAwesomeIcon icon={faLink} /> Link tasks</button>}
          {finished.length > 0 && (
            <button className="btn btn--ghost btn--small" aria-pressed={showFinished} onClick={() => setShowFinished(!showFinished)}>
              <FontAwesomeIcon icon={faCircleCheck} /> {showFinished ? "Hide finished" : `Show finished (${finished.length})`}
            </button>
          )}
          <button className="btn btn--primary btn--small" onClick={onNew}><FontAwesomeIcon icon={faPlus} /> New task</button>
        </div>
      </header>

      {ideas.length > 0 && (
        <ul className="jam-ideas" aria-label="Cadence's suggestions">
          {ideas.map((s) => (
            <li key={s.proposalId} className="jam-idea">
              <span className="jam-idea__mark" aria-hidden="true">C</span>
              <p>
                <strong>Cadence suggests:</strong> “{titles.get(s.to)}” waits on “{titles.get(s.from)}”.
                {s.question && <span className="muted small"> {s.question.replace(/^Does .*?\?\s*/, "")}</span>}
              </p>
              <button className="btn btn--primary btn--small" onClick={() => onAnswer(s.proposalId, "confirm")}>Confirm</button>
              <button className="btn btn--soft btn--small" onClick={() => onAnswer(s.proposalId, "not_now")}>Not now</button>
            </li>
          ))}
        </ul>
      )}

      {withIds.length === 0 ? (
        <p className="muted register__empty">No tasks yet. Add one with “New task”; when tasks need each other, Cadence suggests the link here.</p>
      ) : (
        <Board tasks={withIds} ideas={ideas} nameOf={nameOf} onLink={onLink} onConnect={onConnect} onDisconnect={onDisconnect} />
      )}

      <section className="page__section" aria-labelledby="deps-list">
        <h3 id="deps-list">In words</h3>
        {rows.length === 0 ? (
          <p className="muted small">Nothing waits on anything yet.</p>
        ) : (
          <Capped
            className="deps"
            limit={4}
            title="What waits on what"
            items={rows}
            render={(row) => (
              <li key={row.task.task_id ?? row.task.title} className="deps__row">
                <p className="deps__head">
                  <strong>{row.task.title}</strong>
                  <span className={row.waiting ? "tag tag--warn" : "tag"}>{row.task.status === "done" ? "Done" : row.waiting ? "Waiting" : "Ready to start"}</span>
                  {row.task.task_id && <button className="link-btn" aria-label={`Change what ${row.task.title} waits on`} onClick={() => onLink(row.task.task_id!)}>Change</button>}
                </p>
                <ul className="deps__needs" aria-label={`${row.task.title} waits on`}>
                  {row.needs.map((n) => {
                    const source = row.task.dependency_sources?.[n.task.task_id ?? ""];
                    const why = source ? `Linked ${source.replace(/^card \w+/, "from a card")}` : "Origin of this link not recorded";
                    return (
                      <li key={n.task.task_id ?? n.task.title}>
                        {n.done ? <FontAwesomeIcon icon={faCheck} aria-hidden="true" /> : <span className="deps__open" aria-hidden="true" />}
                        <span className="deps__need">{n.task.title}</span>
                        <span className="muted small">{n.done ? "done" : STATUS_NAMES[n.task.status] ?? n.task.status}</span>
                        <details className="deps__why">
                          <summary className="small">Why?</summary>
                          <span className="muted small">{why}</span>
                        </details>
                      </li>
                    );
                  })}
                </ul>
              </li>
            )}
          />
        )}
      </section>
    </section>
  );
}

function Board({ tasks, ideas, nameOf, onLink, onConnect, onDisconnect }: { tasks: Task[]; ideas: Suggestion[]; nameOf: (id?: MemberId | null) => string | undefined; onLink: (taskId: string) => void; onConnect?: (from: string, to: string) => void; onDisconnect?: (from: string, to: string) => void }) {
  const auto = useMemo(() => startPositions(tasks, ideas), [tasks, ideas]);
  const [moved, setMoved] = useState<Record<string, Point>>(savedPositions);
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 });
  const drag = useRef<{ kind: "note" | "pan" | "wire" | "cut"; id?: string; waits?: string; start: Point; origin: Point; moved: boolean } | null>(null);
  // A link being drawn: from the dot of a note to the pointer (canvas coordinates).
  // `cut` is the waiting note whose existing link is being pulled off by its end dot.
  const [wire, setWire] = useState<{ from: string; to: Point; over: string | null; cut?: string } | null>(null);
  const board = useRef<HTMLDivElement>(null);
  const pos = (id: string): Point => moved[id] ?? auto[id] ?? { x: PAD, y: PAD };
  const waiting = new Set(waitingOn(tasks).filter((w) => w.waiting).map((w) => w.task.task_id));
  const titles = new Map(tasks.map((t) => [t.task_id!, t.title]));

  const edges = tasks.flatMap((t) => (t.depends_on ?? []).filter((d) => auto[d] || moved[d]).map((d) => ({ from: d, to: t.task_id!, done: tasks.find((x) => x.task_id === d)?.status === "done" })));

  const fit = useCallback(() => {
    const el = board.current;
    if (!el) return;
    const all = tasks.map((t) => pos(t.task_id!));
    const width = Math.max(...all.map((p) => p.x)) + NOTE_W + PAD;
    const height = Math.max(...all.map((p) => p.y)) + NOTE_H + PAD;
    const zoom = Math.max(0.4, Math.min(1, el.clientWidth / width, el.clientHeight / height));
    setView({ x: 0, y: 0, zoom });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tasks, moved, auto]);
  useEffect(() => fit(), [tasks.length]); // eslint-disable-line react-hooks/exhaustive-deps

  /** The pointer in canvas coordinates (the canvas is panned and zoomed). */
  const onCanvas = (e: { clientX: number; clientY: number }): Point => {
    const box = board.current?.getBoundingClientRect();
    return { x: (e.clientX - (box?.left ?? 0) - view.x) / view.zoom, y: (e.clientY - (box?.top ?? 0) - view.y) / view.zoom };
  };
  /** The note under the pointer, if any (its id). */
  const noteAt = (e: { clientX: number; clientY: number }) =>
    (document.elementFromPoint?.(e.clientX, e.clientY)?.closest("[data-task]") as HTMLElement | null)?.dataset.task ?? null;

  const down = (e: ReactPointerEvent, kind: "note" | "pan" | "wire" | "cut", id?: string, waits?: string) => {
    if (e.button !== 0) return;
    if ((kind === "wire" || kind === "cut") && id) {
      e.stopPropagation();
      drag.current = { kind, id, waits, start: { x: e.clientX, y: e.clientY }, origin: pos(id), moved: false };
      (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
      setWire({ from: id, to: onCanvas(e), over: null, cut: waits });
      return;
    }
    const origin = kind === "note" && id ? pos(id) : { x: view.x, y: view.y };
    drag.current = { kind, id, start: { x: e.clientX, y: e.clientY }, origin, moved: false };
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    if (kind === "note") e.stopPropagation();
  };
  const move = (e: ReactPointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.start.x;
    const dy = e.clientY - d.start.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
    if (d.kind === "wire" || d.kind === "cut") {
      const over = noteAt(e);
      setWire({ from: d.id!, to: onCanvas(e), over: over && over !== d.id ? over : null, cut: d.waits });
      return;
    }
    if (d.kind === "pan") setView((v) => ({ ...v, x: d.origin.x + dx, y: d.origin.y + dy }));
    else if (d.id) setMoved((m) => ({ ...m, [d.id!]: { x: Math.max(0, d.origin.x + dx / view.zoom), y: Math.max(0, d.origin.y + dy / view.zoom) } }));
  };
  const up = (e?: ReactPointerEvent) => {
    const d = drag.current;
    drag.current = null;
    if (d?.kind === "wire") {
      const target = e ? noteAt(e) : null;
      setWire(null);
      if (target && target !== d.id) onConnect?.(d.id!, target);
      return;
    }
    if (d?.kind === "cut") {
      // Pulled off and let go in the open: the link is removed. Let go on any note (or cancel the
      // drag) and the link snaps back unchanged.
      const target = e ? noteAt(e) : null;
      setWire(null);
      if (d.moved && e && !target) onDisconnect?.(d.id!, d.waits!);
      return;
    }
    if (d?.kind === "note" && d.moved) keepPositions(moved);
    if (d?.kind === "note" && !d.moved && d.id) onLink(d.id);
  };
  const zoomBy = (factor: number) => setView((v) => ({ ...v, zoom: Math.max(0.4, Math.min(1.6, v.zoom * factor)) }));
  const tidy = () => {
    const kept = savedPositions();
    for (const t of tasks) delete kept[t.task_id!];
    keepPositions(kept);
    setMoved(kept);
    setTimeout(fit, 0);
  };

  /**
   * An arrow from the note that is needed to the one that waits, leaving from the side that faces it.
   * `end` is where the arrow meets the waiting note: the line stops one dot-radius short of it so the
   * arrowhead touches the dot that sits there (the dot that disconnects the link).
   */
  const route = (a: Point, b: Point): { d: string; end: Point } => {
    const R = PORT / 2;
    if (b.x >= a.x + NOTE_W * 0.75) {
      const x1 = a.x + NOTE_W, y1 = a.y + NOTE_H / 2, x2 = b.x, y2 = b.y + NOTE_H / 2;
      const bend = Math.max(40, (x2 - x1) / 2);
      return { d: `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - R - bend} ${y2}, ${x2 - R} ${y2}`, end: { x: x2, y: y2 } };
    }
    if (b.x + NOTE_W * 0.75 <= a.x) {
      const x1 = a.x, y1 = a.y + NOTE_H / 2, x2 = b.x + NOTE_W, y2 = b.y + NOTE_H / 2;
      const bend = Math.max(40, (x1 - x2) / 2);
      return { d: `M ${x1} ${y1} C ${x1 - bend} ${y1}, ${x2 + R + bend} ${y2}, ${x2 + R} ${y2}`, end: { x: x2, y: y2 } };
    }
    const down = b.y >= a.y;
    const x1 = a.x + NOTE_W / 2, y1 = down ? a.y + NOTE_H : a.y, x2 = b.x + NOTE_W / 2, y2 = down ? b.y : b.y + NOTE_H;
    const bend = Math.max(30, Math.abs(y2 - y1) / 2) * (down ? 1 : -1);
    const ye = down ? y2 - R : y2 + R;
    return { d: `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${ye - bend}, ${x2} ${ye}`, end: { x: x2, y: y2 } };
  };
  const curve = (a: Point, b: Point) => route(a, b).d;
  const size = tasks.reduce((s, t) => {
    const p = pos(t.task_id!);
    return { w: Math.max(s.w, p.x + NOTE_W + PAD), h: Math.max(s.h, p.y + NOTE_H + PAD) };
  }, { w: 600, h: 300 });

  return (
    <div className="jam" aria-label="Dependency board">
      <div className="jam__tools" role="toolbar" aria-label="Board">
        <button className="btn btn--soft btn--round" aria-label="Zoom out" onClick={() => zoomBy(0.85)}><FontAwesomeIcon icon={faMinus} /></button>
        <span className="small jam__zoom" aria-live="polite">{Math.round(view.zoom * 100)}%</span>
        <button className="btn btn--soft btn--round" aria-label="Zoom in" onClick={() => zoomBy(1.15)}><FontAwesomeIcon icon={faPlus} /></button>
        <button className="btn btn--soft btn--small" onClick={fit}><FontAwesomeIcon icon={faUpRightAndDownLeftFromCenter} /> Fit</button>
        <button className="btn btn--soft btn--small" onClick={tidy}>Tidy up</button>
      </div>
      <div
        ref={board}
        className="jam__board"
        onPointerDown={(e) => down(e, "pan")}
        onPointerMove={move}
        onPointerUp={(e) => up(e)}
        onPointerCancel={() => up()}
        onWheel={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoomBy(e.deltaY < 0 ? 1.08 : 0.92); } }}
      >
        <div className="jam__canvas" style={{ width: size.w, height: size.h, transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})` }}>
          <svg className="jam__wires" width={size.w} height={size.h} aria-hidden="true">
            <defs>
              <marker id="jam-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" className="jam__head" /></marker>
              <marker id="jam-arrow-idea" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" className="jam__head jam__head--idea" /></marker>
            </defs>
            {edges.filter((e) => !(wire?.cut === e.to && wire.from === e.from)).map((e) => (
              <g key={`${e.from}-${e.to}`} className="jam__link">
                {/* A wide invisible stroke makes the arrow easy to click: it opens the waiting task's links. */}
                <path d={curve(pos(e.from), pos(e.to))} className="jam__hit" onPointerDown={(ev) => ev.stopPropagation()} onClick={() => onLink(e.to)} />
                <path d={curve(pos(e.from), pos(e.to))} className={`jam__wire${e.done ? " jam__wire--done" : ""}`} markerEnd="url(#jam-arrow)" />
              </g>
            ))}
            {wire && (
              <path
                d={`M ${pos(wire.from).x + NOTE_W} ${pos(wire.from).y + NOTE_H / 2} L ${wire.to.x} ${wire.to.y}`}
                className="jam__wire jam__wire--draft"
                markerEnd="url(#jam-arrow)"
              />
            )}
            {ideas.map((s) => (
              <path key={s.proposalId} d={curve(pos(s.from), pos(s.to))} className="jam__wire jam__wire--idea" markerEnd="url(#jam-arrow-idea)" />
            ))}
          </svg>
          {tasks.map((t, i) => {
            const p = pos(t.task_id!);
            const status = t.status === "done" ? "done" : t.status === "blocked" || waiting.has(t.task_id) ? "waiting" : t.status;
            const owner = t.owner_id ? nameOf(t.owner_id) : null;
            return (
              <button
                key={t.task_id}
                data-task={t.task_id}
                className={`note note--${status}${wire?.over === t.task_id ? " note--target" : ""}`}
                style={{ left: p.x, top: p.y, width: NOTE_W, height: NOTE_H, ["--tilt" as string]: `${((i % 5) - 2) * 0.6}deg` }}
                onPointerDown={(e) => down(e, "note", t.task_id!)}
                title={t.title}
              >
                <span className="note__title">{t.title}</span>
                <span className="note__foot">
                  <span>{owner ?? "No owner"}</span>
                  <span>{status === "done" && <FontAwesomeIcon icon={faCircleCheck} className="note__done" />} {status === "waiting" ? "Waiting" : STATUS_NAMES[t.status] ?? t.status}</span>
                </span>
                <span className="sr-only">Change what it waits on</span>
              </button>
            );
          })}
          {onConnect && tasks.map((t) => {
            const p = pos(t.task_id!);
            return (
              // Pointer only: with the keyboard, the note itself opens the same links in a popup.
              <span
                key={`port-${t.task_id}`}
                className="jam__port"
                style={{ left: p.x + NOTE_W - PORT / 2, top: p.y + NOTE_H / 2 - PORT / 2 }}
                title={`Drag onto the task that waits on “${t.title}”`}
                aria-hidden="true"
                onPointerDown={(e) => down(e, "wire", t.task_id!)}
              />
            );
          })}
          {/* The other end of each arrow: a dot where it meets the waiting note. Pull it off into the open to disconnect. */}
          {onDisconnect && edges.map((e) => {
            const end = route(pos(e.from), pos(e.to)).end;
            // Kept in the page while pulled (it holds the pointer), only hidden: the draft line takes its place.
            const lifted = wire?.cut === e.to && wire.from === e.from;
            return (
              <span
                key={`end-${e.from}-${e.to}`}
                className={`jam__port jam__port--end${lifted ? " jam__port--lifted" : ""}`}
                data-end={`${e.from}>${e.to}`}
                style={{ left: end.x - PORT / 2, top: end.y - PORT / 2 }}
                title={`Drag away to stop “${titles.get(e.to)}” waiting on “${titles.get(e.from)}”`}
                aria-hidden="true"
                onPointerDown={(ev) => down(ev, "cut", e.from, e.to)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
