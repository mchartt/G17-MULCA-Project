import { useEffect, useRef, useState } from "react";

// The scroll film: 436 real frames (film/public/desktop), drawn on a canvas.
// Scrolling moves a target frame; the drawn frame eases toward it, so the film
// plays forward and backward with the scroll and never jumps.
type FilmMeta = { frameCount: number; framePrefix: string; frameIndexDigits: number; firstFrameIndex: number; frameExtension: string };

const BEATS = [
  { from: 0.0, to: 0.3, title: "Group projects drift.", text: "Messages pile up, nobody owns the next step, and the deadline arrives early." },
  { from: 0.34, to: 0.64, title: "Cadence reads along.", text: "It notices when a task has no owner, a decision never closes or work runs late." },
  { from: 0.68, to: 1.01, title: "It proposes. You decide.", text: "Every change to the plan waits for one member's click." },
];

const BASE = "/film/desktop/";

function frameUrl(meta: FilmMeta, i: number) {
  return `${BASE}${meta.framePrefix}${String(i + meta.firstFrameIndex).padStart(meta.frameIndexDigits, "0")}.${meta.frameExtension}`;
}

export function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
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
    const frames: (HTMLImageElement | null)[] = [];
    let meta: FilmMeta | null = null;
    let shown = 0;
    let target = 0;

    const nearestLoaded = (i: number) => {
      for (let d = 0; d < frames.length; d++) {
        if (frames[i - d]?.complete) return frames[i - d];
        if (frames[i + d]?.complete) return frames[i + d];
      }
      return null;
    };

    const draw = () => {
      const c = canvas.current;
      if (!c || !meta) return;
      shown += (target - shown) * 0.18;
      if (Math.abs(target - shown) < 0.01) shown = target;
      const img = nearestLoaded(Math.round(shown));
      const ctx = c.getContext("2d");
      if (img && ctx) {
        const { width: w, height: h } = c;
        const scale = Math.max(w / img.naturalWidth, h / img.naturalHeight);
        const dw = img.naturalWidth * scale;
        const dh = img.naturalHeight * scale;
        ctx.drawImage(img, (w - dw) / 2, (h - dh) / 2, dw, dh);
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
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((m: FilmMeta) => {
        if (!alive) return;
        meta = m;
        frames.length = m.frameCount;
        // Coarse first (every 8th frame), then fill the gaps: the film is scrubbable almost at once.
        for (const stride of [8, 4, 2, 1]) {
          for (let i = 0; i < m.frameCount; i += stride) {
            if (frames[i]) continue;
            const img = new Image();
            img.decoding = "async";
            img.src = frameUrl(m, i);
            frames[i] = img;
          }
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
        <div className="film__cards">
          <h1 id="film-title" className="sr-only">Cadence</h1>
          {BEATS.map((b) => (
            <div className="index-card" key={b.title}>
              <p className="index-card__title">{b.title}</p>
              <p>{b.text}</p>
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
        <h1 id="film-title" className="film__brand">Cadence</h1>
        {BEATS.map((b) => {
          const visible = progress >= b.from && progress < b.to;
          return (
            <div key={b.title} className={`index-card index-card--beat${visible ? " is-visible" : ""}`} aria-hidden={!visible}>
              <p className="index-card__title">{b.title}</p>
              <p>{b.text}</p>
            </div>
          );
        })}
        <a className="film__skip" href="#how">Skip the film</a>
        <p className={`film__hint${progress > 0.02 ? " is-gone" : ""}`} aria-hidden="true">Scroll</p>
      </div>
    </section>
  );
}
