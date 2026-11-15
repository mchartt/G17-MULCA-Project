// Motion helpers: smooth scroll (Lenis) and reveal-on-view. Both switch off with
// prefers-reduced-motion. Reveals play once, when the element first enters.
import Lenis from "lenis";
import { useEffect, useRef } from "react";

export function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function useSmoothScroll(enabled: boolean): void {
  useEffect(() => {
    if (!enabled || prefersReducedMotion()) return;
    const lenis = new Lenis({ duration: 1.1, easing: (t) => 1 - Math.pow(1 - t, 3) });
    let raf = 0;
    const loop = (time: number) => {
      lenis.raf(time);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      lenis.destroy();
    };
  }, [enabled]);
}

/** Adds the class `is-in` the first time the element is 15 % visible. */
export function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (prefersReducedMotion() || typeof IntersectionObserver === "undefined") {
      el.classList.add("is-in");
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries)
          if (e.isIntersecting) {
            e.target.classList.add("is-in");
            io.unobserve(e.target);
          }
      },
      { threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return ref;
}

/** Scroll progress (0..1) of an element through the viewport, for scrubbed effects. */
export function useScrollProgress<T extends HTMLElement>(onProgress: (p: number) => void) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const update = () => {
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const p = (innerHeight - r.top) / (innerHeight + r.height * 0.4);
      onProgress(Math.min(1, Math.max(0, p)));
    };
    update();
    addEventListener("scroll", update, { passive: true });
    return () => removeEventListener("scroll", update);
  }, [onProgress]);
  return ref;
}
