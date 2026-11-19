import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState, type FormEvent } from "react";
import { createMySpace, joinMySpace, openMySpace, type SpaceRef, type User } from "../lib/account";
import { ApiError, saveToken } from "../lib/api";
import { faArrowRight, faRightFromBracket, faUserPen } from "../lib/icons";
import { ProfileForm } from "./ProfileForm";

type Props = {
  user: User;
  spaces: SpaceRef[];
  disabled: boolean;
  onEnter: (spaceToken: string) => void;
  onUser: (user: User) => void;
  onLogout: () => void;
};

/** A logged-in person's home: their spaces, a new space, an invite code, their profile. */
export function Home({ user, spaces, disabled, onEnter, onUser, onLogout }: Props) {
  const [project, setProject] = useState("");
  const [code, setCode] = useState(() => new URLSearchParams(location.search).get("code") ?? "");
  const invited = new URLSearchParams(location.search).has("code");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ where: string; text: string } | null>(null);
  const [editing, setEditing] = useState(false);

  /** Every way in ends the same: a space token, saved, and the console opens. */
  async function enter(where: string, open: () => Promise<{ token: string }>) {
    setBusy(where);
    setError(null);
    try {
      const { token } = await open();
      saveToken(token);
      onEnter(token);
    } catch (err) {
      setError({ where, text: err instanceof ApiError ? err.message : "Something went wrong. Try again." });
    } finally {
      setBusy(null);
    }
  }

  const create = (e: FormEvent) => { e.preventDefault(); void enter("create", () => createMySpace(project)); };
  const join = (e: FormEvent) => { e.preventDefault(); void enter("join", () => joinMySpace(code)); };
  const off = disabled || busy !== null;
  const createForm = (
    <form key="create" className="panel-card form" onSubmit={create}>
      <h3>Start a new space</h3>
      <label htmlFor="c-project">Project name</label>
      <input id="c-project" value={project} onChange={(e) => setProject(e.target.value)} maxLength={80} required placeholder="AUI group project" />
      {error?.where === "create" && <p className="form__error" role="alert">{error.text}</p>}
      <button className="btn btn--primary" type="submit" disabled={off}>
        {busy === "create" ? "Creating…" : "Create the space"} <FontAwesomeIcon icon={faArrowRight} />
      </button>
    </form>
  );
  const joinForm = (
    <form key="join" className={`panel-card form${invited ? " form--invited" : ""}`} onSubmit={join}>
      <h3>{invited ? "You are invited" : "Join with an invite code"}</h3>
      <label htmlFor="j-code">Invite code</label>
      <input id="j-code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={20} required className="code-field" spellCheck={false} />
      {error?.where === "join" && <p className="form__error" role="alert">{error.text}</p>}
      <button className={`btn ${invited ? "btn--primary" : "btn--dark"}`} type="submit" disabled={off}>
        {busy === "join" ? "Joining…" : "Join the space"} <FontAwesomeIcon icon={faArrowRight} />
      </button>
    </form>
  );

  return (
    <div className="home">
      <div className="home__who">
        <p>Logged in as <strong>{user.displayName}</strong> <span className="muted">({user.email})</span></p>
        <div className="home__actions">
          <button className="btn btn--soft btn--small" aria-expanded={editing} onClick={() => setEditing(!editing)}><FontAwesomeIcon icon={faUserPen} /> My profile</button>
          <button className="btn btn--link" onClick={onLogout}><FontAwesomeIcon icon={faRightFromBracket} /> Log out</button>
        </div>
      </div>

      {editing && (
        <div className="panel-card home__profile">
          <h3>My profile</h3>
          <ProfileForm user={user} onSaved={onUser} onCancel={() => setEditing(false)} />
        </div>
      )}

      {spaces.length > 0 && (
        <div className="home__spaces">
          <h3>Your spaces</h3>
          <ul>
            {spaces.map((s) => (
              <li key={s.id} className="panel-card">
                <span><strong>{s.name}</strong> <code className="muted">{s.inviteCode}</code></span>
                <button className="btn btn--primary btn--small" disabled={off} onClick={() => void enter(`open-${s.id}`, () => openMySpace(s.id))}>
                  {busy === `open-${s.id}` ? "Opening…" : "Open"} <FontAwesomeIcon icon={faArrowRight} />
                </button>
                {error?.where === `open-${s.id}` && <p className="form__error" role="alert">{error.text}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Arriving from an invite link, joining comes first. */}
      <div className="entry__forms">
        {invited ? <>{joinForm}{createForm}</> : <>{createForm}{joinForm}</>}
      </div>
    </div>
  );
}
