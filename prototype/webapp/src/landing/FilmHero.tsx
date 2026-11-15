import { useEffect, useRef, useState } from "react";
import { prefersReducedMotion } from "../lib/motion";

// The scroll film: 436 real frames drawn on a canvas. Scrolling sets a target
// frame; the drawn frame eases toward it, so the film follows the scroll both
// ways without jumps. Three large titles appear over it, scrubbed by the scroll.
type FilmMeta = { frameCount: number; framePrefix: string; frameIndexDigits: number; firstFrameIndex: number; frameExtension: string };

const BEATS = [
  { at: 0.12, title: "Group projects drift.", text: "Messages pile up, nobody owns the next step, and the deadline arrives early." },
  { at: 0.48, title: "Cadence reads along.", text: "It notices when a task has no owner, a decision never closes or work runs late." },
  { at: 0.84, title: "It proposes. You decide.", text: "Every change to the plan waits for one member's click." },
];
const HALF_WIDTH = 0.16; // how much scroll each title stays on screen, either side of its centre

const BASE = "/film/desktop/";
const frameUrl = (m: FilmMeta, i: number) =>
  `${BASE}${m.framePrefix}${String(i + m.firstFrameIndex).padStart(m.frameIndexDigits, "0")}.${m.frameExtension}`;

/** 0 far from the beat, 1 at its centre, with a soft shoulder (smoothstep). */
export function beatOpacity(progress: number, at: number, first = false, last = false): number {
  // The first title is fully there at the top of the page, the last one stays until the end.
  if ((first && progress <= at) || (last && progress >= at)) return 1;
  const d = Math.abs(progress - at) / HALF_WIDTH;
  if (d >= 1) return 0;
  const t = Math.min(1, (1 - d) / 0.5);
  return t * t * (3 - 2 * t);
}

export function FilmHero() {
  const reduced = prefersReducedMotion();
  const section = useRef<HTMLElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [progress, setProgress] = useState(0);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (reduced) return;
    let alive = true;
    let raf = 0;
    const frames: (HTMLImageElement | undefined)[] = [];
    let meta: FilmMeta | null = null;
    let shown = 0;
    let target = 0;

    const nearestLoaded = (i: number) => {
      for (let d = 0; d < frames.length; d++) {
        const a = frames[i - d];
        if (a?.complete && a.naturalWidth) return a;
        const b = frames[i + d];
        if (b?.complete && b.naturalWidth) return b;
      }
      return null;
    };

    const draw = () => {
      const c = canvas.current;
      if (c && meta) {
        shown += (target - shown) * 0.14;
        const img = nearestLoaded(Math.round(shown));
        const ctx = c.getContext("2d");
        if (img && ctx) {
          const scale = Math.max(c.width / img.naturalWidth, c.height / img.naturalHeight);
          const w = img.naturalWidth * scale;
          const h = img.naturalHeight * scale;
          ctx.drawImage(img, (c.width - w) / 2, (c.height - h) / 2, w, h);
        }
      }
      raf = requestAnimationFrame(draw);
    };

    const onScroll = () => {
      const el = section.current;
      if (!el) return;
      const total = el.offsetHeight - innerHeight;
      const p = Math.min(1, Math.max(0, -el.getBoundingClientRect().top / Math.max(1, total)));
      setProgress(p);
      if (meta) target = p * (meta.frameCount - 1);
    };

    const onResize = () => {
      const c = canvas.current;
      if (!c) return;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      c.width = Math.round(c.clientWidth * dpr);
      c.height = Math.round(c.clientHeight * dpr);
    };

    fetch(`${BASE}film.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("no film"))))
      .then((m: FilmMeta) => {
        if (!alive) return;
        meta = m;
        frames.length = m.frameCount;
        // Coarse first (every 8th frame), then fill the gaps: scrubbable almost at once.
        for (const stride of [8, 4, 2, 1])
          for (let i = 0; i < m.frameCount; i += stride) {
            if (frames[i]) continue;
            const img = new Image();
            img.decoding = "async";
            img.src = frameUrl(m, i);
            frames[i] = img;
          }
        onResize();
        onScroll();
        raf = requestAnimationFrame(draw);
      })
      .catch(() => alive && setFailed(true));

    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("resize", onResize);
    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      removeEventListener("scroll", onScroll);
      removeEventListener("resize", onResize);
    };
  }, [reduced]);

  if (reduced || failed) {
    return (
      <section className="film film--still" aria-labelledby="film-title">
        <img className="film__still" src={`${BASE}f_0436.jpg`} alt="A cork board in morning light, with paper cards pinned in three tidy columns." />
        <div className="film__scrim" />
        <div className="film__stack">
          <h1 id="film-title" className="sr-only">Cadence</h1>
          {BEATS.map((b) => (
            <div key={b.title} className="beat beat--static">
              <p className="beat__title">{b.title}</p>
              <p className="beat__text">{b.text}</p>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section ref={section} className="film" aria-labelledby="film-title">
      <div className="film__sticky">
        <canvas ref={canvas} className="film__canvas" role="img" aria-label="A dark study room with paper notes hanging in the air; scrolling moves toward a cork board where the notes are pinned into a clear plan." />
        <div className="film__scrim" />
        <h1 id="film-title" className="sr-only">Cadence</h1>
        {BEATS.map((b, i) => {
          const o = beatOpacity(progress, b.at, i === 0, i === BEATS.length - 1);
          return (
            <div
              key={b.title}
              className="beat"
              aria-hidden={o < 0.5}
              style={{ opacity: o, transform: `translate3d(-50%, ${(1 - o) * 24}px, 0) scale(${0.97 + o * 0.03})` }}
            >
              <p className="beat__title">{b.title}</p>
              <p className="beat__text">{b.text}</p>
            </div>
          );
        })}
        <p className="film__hint" style={{ opacity: progress > 0.02 ? 0 : 1 }} aria-hidden="true">
          Scroll to begin
        </p>
      </div>
    </section>
  );
}
