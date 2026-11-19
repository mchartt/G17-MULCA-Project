import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { initials } from "../console/Chat";
import { Dialog } from "../console/Dialogs";
import { joinMySpace, openMySpace, type SpaceRef, type User } from "../lib/account";
import { ApiError, saveToken } from "../lib/api";
import { faArrowRight, faChevronLeft, faChevronRight, faMagnifyingGlass, faPlus, faRightFromBracket, faShieldHalved, faUserPen } from "../lib/icons";
import { codeInAddress } from "../lib/invite";
import { PrivacyNotice } from "./LoginPage";
import { ProfileForm } from "./ProfileForm";

type Props = {
  user: User;
  spaces: SpaceRef[];
  disabled: boolean;
  onEnter: (spaceToken: string) => void;
  /** Go to the setup desk (/login/new). */
  onNew: () => void;
  onUser: (user: User) => void;
  onLogout: () => void;
};

/** Every way in ends the same: a space token, saved, and the console opens. */
async function openWith(open: () => Promise<{ token: string }>, onEnter: (token: string) => void): Promise<string | null> {
  try {
    const { token } = await open();
    saveToken(token);
    onEnter(token);
    return null;
  } catch (err) {
    return err instanceof ApiError ? err.message : "Something went wrong. Try again.";
  }
}

/**
 * Join a teammate's space with the invite code (filled in when you arrive from an invite link).
 * A card in the guided setup; on the home, a compact field beside "New project",
 * because joining and creating are the two ways to start.
 */
export function JoinForm({ disabled, onEnter, title, inline = false }: { disabled: boolean; onEnter: (token: string) => void; title?: string; inline?: boolean }) {
  const [code, setCode] = useState(codeInAddress);
  const invited = codeInAddress() !== "";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const join = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(await openWith(() => joinMySpace(code), onEnter));
    setBusy(false);
  };
  const button = (
    <button className={`btn ${invited ? "btn--primary" : "btn--dark"}`} type="submit" disabled={disabled || busy}>
      {busy ? "Joining…" : "Join the space"} <FontAwesomeIcon icon={faArrowRight} />
    </button>
  );
  const field = <input id="j-code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={20} required className="code-field" spellCheck={false} placeholder="AB12CD" aria-describedby="j-code-hint" />;
  const hint = <p id="j-code-hint" className="muted small">{invited ? "You have an invite: the code is already filled in." : "A teammate finds it in the room box of their space, at the bottom left."}</p>;

  if (inline) {
    return (
      <form className={`joinbar${invited ? " joinbar--invited" : ""}`} onSubmit={join} aria-label="Join a project">
        <label htmlFor="j-code" className="sr-only">Invite code</label>
        <input id="j-code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={20} required className="code-field" spellCheck={false} placeholder="Invite code" aria-describedby="j-code-hint" title="A teammate finds it in the room box of their space, at the bottom left." />
        {button}
        <p id="j-code-hint" className="sr-only">A teammate finds it in the room box of their space, at the bottom left.</p>
        {error && <p className="form__error joinbar__error" role="alert">{error}</p>}
      </form>
    );
  }
  return (
    <form className={`panel-card form${invited ? " form--invited" : ""}`} onSubmit={join}>
      <h3>{title ?? (invited ? "You are invited" : "Join with an invite code")}</h3>
      <label htmlFor="j-code">Invite code</label>
      {field}
      {hint}
      {error && <p className="form__error" role="alert">{error}</p>}
      {button}
    </form>
  );
}

/* The project tiles: their size is fixed (shorter on a phone, set by --tile-h in home.css), so the page knows how many fit. */
const TILE_H = 92;
const TILE_MIN_W = 236;
const GAP = 12;

/**
 * How many tiles fit in the box without scrolling: as many columns as its
 * width allows and as many rows as its height allows. A browser without
 * ResizeObserver (and the unit tests) gets three columns by two rows.
 */
function useFit(box: RefObject<HTMLElement | null>) {
  const [fit, setFit] = useState({ cols: 3, rows: 2, tile: TILE_H });
  useLayoutEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      // The box has a little padding, so a tile's focus ring is not cut off.
      const css = getComputedStyle(el);
      const width = el.clientWidth - parseFloat(css.paddingLeft) - parseFloat(css.paddingRight);
      const height = el.clientHeight - parseFloat(css.paddingTop) - parseFloat(css.paddingBottom);
      if (width <= 0 || height <= 0) return;
      const tile = parseFloat(css.getPropertyValue("--tile-h")) || TILE_H;
      const cols = Math.max(1, Math.floor((width + GAP) / (TILE_MIN_W + GAP)));
      const rows = Math.max(1, Math.floor((height + GAP) / (tile + GAP)));
      setFit((f) => (f.cols === cols && f.rows === rows && f.tile === tile ? f : { cols, rows, tile }));
    };
    const watch = new ResizeObserver(measure);
    watch.observe(el);
    measure();
    return () => watch.disconnect();
  }, [box]);
  return fit;
}

/** A soft colour per project, from its name, so a long list is easier to scan. Decoration only: the name is always written. */
const HUES = [252, 200, 162, 28, 330, 285];
function hue(name: string) {
  let h = 0;
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return HUES[h % HUES.length]!;
}

/** The profile in a few words, so you see what Cadence knows about you; empty, an invitation to fill it. */
function ProfileFacts({ user, onEdit }: { user: User; onEdit: () => void }) {
  const skills = user.skills.slice(0, 3);
  const more = user.skills.length - skills.length;
  if (!user.discipline.trim() && user.skills.length === 0 && user.weeklyHours === null) {
    return (
      <button className="me__empty btn btn--link btn--small" onClick={onEdit}>
        Add what you study and your skills: Cadence uses them to suggest who could take a task.
      </button>
    );
  }
  return (
    <ul className="me__facts" aria-label="Your profile">
      {user.discipline.trim() && <li className="me__fact me__fact--study">{user.discipline}</li>}
      {skills.map((s) => <li key={s} className="me__fact">{s}</li>)}
      {more > 0 && <li className="me__fact me__fact--more">+{more} skills</li>}
      {user.weeklyHours !== null && <li className="me__fact me__fact--hours">{user.weeklyHours} h a week</li>}
    </ul>
  );
}

/**
 * A logged-in person's home, sized to the window: a slim strip with who you
 * are, then your projects across the whole width, a page at a time (never a
 * long scroll). The two ways to start sit together beside the title: join
 * with a code, or a new project (the setup desk).
 */
export function Home({ user, spaces, disabled, onEnter, onNew, onUser, onLogout }: Props) {
  const invited = codeInAddress() !== "";
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<{ name: string; text: string } | null>(null);
  const [profile, setProfile] = useState(false);
  const [privacy, setPrivacy] = useState(() => location.hash === "#privacy");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const { cols, rows, tile } = useFit(box);

  // The nav's "Privacy" link (/login#privacy) opens the notice here too.
  useEffect(() => {
    const onHash = () => location.hash === "#privacy" && setPrivacy(true);
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);
  const closePrivacy = () => {
    setPrivacy(false);
    if (location.hash === "#privacy") history.replaceState(null, "", location.pathname + location.search);
  };

  async function open(space: SpaceRef) {
    setBusy(space.id);
    setError(null);
    const text = await openWith(() => openMySpace(space.id), onEnter);
    if (text) setError({ name: space.name, text });
    setBusy(null);
  }

  const perPage = cols * rows;
  const needle = query.trim().toLowerCase();
  const found = needle ? spaces.filter((s) => s.name.toLowerCase().includes(needle) || s.inviteCode.toLowerCase().includes(needle)) : spaces;
  const pages = Math.max(1, Math.ceil(found.length / perPage));
  const current = Math.min(page, pages - 1);
  const shown = found.slice(current * perPage, (current + 1) * perPage);

  return (
    <div className="home">
      <header className="me" aria-label="Your account">
        <span className="me__avatar" aria-hidden="true">{initials(user.displayName)}</span>
        <div className="me__id">
          <p className="me__name">{user.displayName}</p>
          <p className="me__email" title={user.email}>{user.email}</p>
        </div>
        <ProfileFacts user={user} onEdit={() => setProfile(true)} />
        <div className="me__actions">
          <button className="btn btn--soft btn--small" onClick={() => setProfile(true)}><FontAwesomeIcon icon={faUserPen} /> My profile</button>
          <button id="privacy" className="btn btn--link btn--small" onClick={() => setPrivacy(true)} aria-label="Privacy: what Cadence reads and keeps">
            <FontAwesomeIcon icon={faShieldHalved} /> Privacy
          </button>
          <button className="btn btn--link btn--small" onClick={onLogout}><FontAwesomeIcon icon={faRightFromBracket} /> Log out</button>
        </div>
      </header>

      <section className="projects" aria-labelledby="home-title">
        <div className="projects__head">
          <h1 id="home-title">
            Your projects{spaces.length > 0 && <span className="projects__count"> {spaces.length}</span>}
          </h1>
          {spaces.length > perPage && (
            <div className="projects__find">
              <FontAwesomeIcon icon={faMagnifyingGlass} aria-hidden="true" />
              <label className="sr-only" htmlFor="p-find">Find a project</label>
              <input
                id="p-find"
                type="search"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setPage(0); }}
                placeholder="Find by name or code"
              />
            </div>
          )}
          {/* The two ways to start, side by side: someone else's project, or a new one. */}
          <div className="projects__start">
            <JoinForm inline disabled={disabled} onEnter={onEnter} />
            <span className="projects__or" aria-hidden="true">or</span>
            <button className="btn btn--primary" onClick={onNew} disabled={disabled}>
              <FontAwesomeIcon icon={faPlus} /> New project
            </button>
          </div>
        </div>
        {invited && <p className="projects__invite" role="status">You have an invite: the code is filled in. Press Join the space.</p>}

        <div className="projects__box" ref={box}>
          {spaces.length === 0 ? (
            <div className="projects__empty">
              <p className="projects__empty-title">No projects yet.</p>
              <p className="muted">Start one with New project: you lay the assignment and your notes on the setup desk. Joining a teammate's? Paste their invite code beside it; they find it in the room box of their space.</p>
            </div>
          ) : found.length === 0 ? (
            <div className="projects__empty">
              <p className="projects__empty-title">No project matches “{query.trim()}”.</p>
              <button className="btn btn--soft btn--small" onClick={() => setQuery("")}>Show all projects</button>
            </div>
          ) : (
            <ul className="projects__grid" aria-label="Projects" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridAutoRows: `${tile}px`, gap: `${GAP}px` }}>
              {shown.map((s) => (
                <li key={s.id}>
                  <button
                    className="tile"
                    style={{ ["--hue" as string]: hue(s.name) }}
                    disabled={disabled || busy !== null}
                    onClick={() => void open(s)}
                    aria-label={`Open ${s.name}`}
                  >
                    <span className="tile__mark" aria-hidden="true">{initials(s.name)}</span>
                    <span className="tile__text">
                      <strong className="tile__name">{s.name}</strong>
                      <code className="tile__code">{s.inviteCode}</code>
                    </span>
                    <span className="tile__go" aria-hidden="true">
                      {busy === s.id ? "Opening…" : <>Open <FontAwesomeIcon icon={faArrowRight} /></>}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="projects__foot">
          {error && <p className="form__error" role="alert">{error.name}: {error.text}</p>}
          {pages > 1 && (
            <nav className="pager" aria-label="Pages of projects">
              <button className="btn btn--soft btn--round" onClick={() => setPage(current - 1)} disabled={current === 0} aria-label="Previous page">
                <FontAwesomeIcon icon={faChevronLeft} />
              </button>
              <span className="pager__where" aria-live="polite">Page {current + 1} of {pages}</span>
              <button className="btn btn--soft btn--round" onClick={() => setPage(current + 1)} disabled={current >= pages - 1} aria-label="Next page">
                <FontAwesomeIcon icon={faChevronRight} />
              </button>
            </nav>
          )}
        </div>

      </section>

      <Dialog open={profile} title="My profile" onClose={() => setProfile(false)}>
        {profile && <ProfileForm user={user} onSaved={onUser} onCancel={() => setProfile(false)} />}
      </Dialog>
      <Dialog open={privacy} title="What Cadence reads and keeps" onClose={closePrivacy}>
        <PrivacyNotice heading={false} />
        <div className="form__actions">
          <button className="btn btn--soft" onClick={closePrivacy}>Close</button>
        </div>
      </Dialog>
    </div>
  );
}
