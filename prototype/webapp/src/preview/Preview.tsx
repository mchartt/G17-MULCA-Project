import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useState, type MouseEvent } from "react";
import { faArrowLeft } from "../lib/icons";
import { CatchUp } from "./CatchUp";
import { Connections } from "./Connections";
import { PlanWeek } from "./PlanWeek";
import { Reflection } from "./Reflection";

/**
 * Preview screens: where Cadence is going, drawn with sample data (sample.ts).
 * They need no space, no token and no server, so they also work on the static
 * site. Every screen says "Preview · sample data": nothing here is connected.
 */
export const VIEWS = [
  { path: "connections", label: "Connections", view: Connections },
  { path: "plan", label: "Plan around calendars", view: PlanWeek },
  { path: "catch-up", label: "Catch up", view: CatchUp },
  { path: "reflection", label: "Reflection", view: Reflection },
] as const;

export type ViewPath = (typeof VIEWS)[number]["path"];

/** "/preview/plan" -> "plan"; anything else under /preview -> the first screen. */
export function viewFromPath(pathname: string): ViewPath {
  const name = pathname.replace(/^\/preview\/?/, "").replace(/\/$/, "");
  return VIEWS.find((v) => v.path === name)?.path ?? VIEWS[0].path;
}

export function Preview() {
  const [path, setPath] = useState<ViewPath>(() => viewFromPath(location.pathname));

  useEffect(() => {
    const onPop = () => setPath(viewFromPath(location.pathname));
    addEventListener("popstate", onPop);
    return () => removeEventListener("popstate", onPop);
  }, []);

  function go(e: MouseEvent, next: ViewPath) {
    if (e.metaKey || e.ctrlKey || e.shiftKey) return; // a new tab stays a new tab
    e.preventDefault();
    history.pushState(null, "", `/preview/${next}`);
    setPath(next);
    scrollTo(0, 0);
  }

  const View = VIEWS.find((v) => v.path === path)!.view;
  return (
    <div className="preview">
      <header className="preview__bar">
        <a className="btn btn--link" href="/"><FontAwesomeIcon icon={faArrowLeft} /> Cadence</a>
        <nav aria-label="Preview screens">
          {VIEWS.map((v) => (
            <a key={v.path} href={`/preview/${v.path}`} aria-current={v.path === path ? "page" : undefined} onClick={(e) => go(e, v.path)}>
              {v.label}
            </a>
          ))}
        </nav>
        <span className="tag tag--sample">Preview · sample data</span>
      </header>
      <main className="preview__main">
        <View />
      </main>
      <footer className="foot">
        <p>These screens show where Cadence is going. Nothing on them is connected or saved; the names and numbers are examples.</p>
      </footer>
    </div>
  );
}
