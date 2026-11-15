import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useEffect, useState, type FormEvent } from "react";
import { adapterOnline, ApiError, createSpace, joinSpace, saveToken } from "../lib/api";
import { faArrowRight, faEye, faHandPointer, faLock, faShieldHalved, faWifi } from "../lib/icons";
import { useReveal } from "../lib/motion";

const NOTICE = [
  { icon: faEye, text: "It reads the messages written in your group's space, so it can notice what needs coordinating." },
  { icon: faLock, text: "It keeps your display name and, if you add them, your discipline, skills and weekly hours." },
  { icon: faShieldHalved, text: "Messages are sent to Azure OpenAI to write Cadence's answers and proposals." },
  { icon: faHandPointer, text: "It never scores or ranks people, and nothing in the plan changes until a member confirms it." },
];

/** Create a space or join one, after reading what Cadence reads and keeps (UC1). */
export function Entry({ onEnter }: { onEnter: (token: string) => void }) {
  const [online, setOnline] = useState<boolean | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [name, setName] = useState("");
  const [project, setProject] = useState("");
  const [code, setCode] = useState(() => new URLSearchParams(location.search).get("code") ?? "");
  const [busy, setBusy] = useState<"create" | "join" | null>(null);
  const [error, setError] = useState<{ form: "create" | "join"; text: string } | null>(null);
  const forms = useReveal<HTMLDivElement>();

  useEffect(() => {
    void adapterOnline().then(setOnline);
  }, []);

  async function run(form: "create" | "join", e: FormEvent) {
    e.preventDefault();
    if (!agreed) {
      setError({ form, text: "Read what Cadence reads and keeps, then tick the box." });
      return;
    }
    setBusy(form);
    setError(null);
    try {
      const result = form === "create" ? await createSpace(project, name) : await joinSpace(code, name);
      saveToken(result.token);
      onEnter(result.token);
    } catch (err) {
      setError({ form, text: err instanceof ApiError ? err.message : "Something went wrong. Try again." });
    } finally {
      setBusy(null);
    }
  }

  const disabled = busy !== null || online === false;

  return (
    <section id="enter" className="entry" aria-labelledby="entry-title">
      <h2 id="entry-title">Open your group's space.</h2>

      {online === false && (
        <div className="offline" role="status">
          <FontAwesomeIcon icon={faWifi} />
          <p>
            This online version shows Cadence's design. Group spaces run on the coordinator server, which is started for the demo
            and for user tests: the forms below work there.
          </p>
        </div>
      )}

      <div id="privacy" className="notice">
        <h3>What Cadence reads and keeps</h3>
        <ul>
          {NOTICE.map((n) => (
            <li key={n.text}>
              <span className="notice__icon"><FontAwesomeIcon icon={n.icon} /></span>
              {n.text}
            </li>
          ))}
        </ul>
        <label className="check">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          I have read this and I agree
        </label>
      </div>

      <div ref={forms} className="entry__forms reveal">
        <form className="panel-card form" onSubmit={(e) => run("create", e)}>
          <h3>Start a new space</h3>
          <label htmlFor="c-name">Your name</label>
          <input id="c-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required autoComplete="given-name" />
          <label htmlFor="c-project">Project name</label>
          <input id="c-project" value={project} onChange={(e) => setProject(e.target.value)} maxLength={80} required placeholder="AUI group project" />
          {error?.form === "create" && <p className="form__error" role="alert">{error.text}</p>}
          <button className="btn btn--primary" type="submit" disabled={disabled}>
            {busy === "create" ? "Creating…" : "Create the space"} <FontAwesomeIcon icon={faArrowRight} />
          </button>
        </form>

        <form className="panel-card form" onSubmit={(e) => run("join", e)}>
          <h3>Join with an invite code</h3>
          <label htmlFor="j-name">Your name</label>
          <input id="j-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required autoComplete="given-name" />
          <label htmlFor="j-code">Invite code</label>
          <input id="j-code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={20} required className="code-field" spellCheck={false} />
          {error?.form === "join" && <p className="form__error" role="alert">{error.text}</p>}
          <button className="btn btn--dark" type="submit" disabled={disabled}>
            {busy === "join" ? "Joining…" : "Join the space"} <FontAwesomeIcon icon={faArrowRight} />
          </button>
        </form>
      </div>
    </section>
  );
}
