import { useState, type FormEvent } from "react";
import { ApiError, createSpace, joinSpace, saveToken } from "../lib/api";

/** Create a space or join one, after reading what Cadence reads and keeps (UC1). */
export function Entry({ onEnter }: { onEnter: (token: string) => void }) {
  const [agreed, setAgreed] = useState(false);
  const [name, setName] = useState("");
  const [project, setProject] = useState("");
  const [code, setCode] = useState(() => new URLSearchParams(location.search).get("code") ?? "");
  const [busy, setBusy] = useState<"create" | "join" | null>(null);
  const [error, setError] = useState<{ form: "create" | "join"; text: string } | null>(null);

  async function run(form: "create" | "join", e: FormEvent) {
    e.preventDefault();
    if (!agreed) {
      setError({ form, text: "Read the data notice above and tick the box first." });
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

  return (
    <section id="enter" className="entry" aria-labelledby="entry-title">
      <h2 id="entry-title">Open your group's space</h2>

      <div className="notice">
        <h3>What Cadence reads and keeps</h3>
        <ul>
          <li>It reads the messages written in your group's space, so it can notice what needs coordinating.</li>
          <li>It keeps your display name and, if you add them, your discipline, skills and weekly hours.</li>
          <li>Messages are sent to Azure OpenAI to write Cadence's answers and proposals.</li>
          <li>It never scores or ranks people, and nothing in the plan changes until a member confirms it.</li>
        </ul>
        <label className="check">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          I have read this and I agree
        </label>
      </div>

      <div className="entry__forms">
        <form className="form" onSubmit={(e) => run("create", e)}>
          <h3>Start a new space</h3>
          <label htmlFor="c-name">Your name</label>
          <input id="c-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required autoComplete="given-name" />
          <label htmlFor="c-project">Project name</label>
          <input id="c-project" value={project} onChange={(e) => setProject(e.target.value)} maxLength={80} required placeholder="AUI group project" />
          {error?.form === "create" && <p className="form__error" role="alert">{error.text}</p>}
          <button className="btn btn--confirm" type="submit" disabled={busy !== null}>{busy === "create" ? "Creating…" : "Create the space"}</button>
        </form>

        <form className="form" onSubmit={(e) => run("join", e)}>
          <h3>Join with an invite code</h3>
          <label htmlFor="j-name">Your name</label>
          <input id="j-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required autoComplete="given-name" />
          <label htmlFor="j-code">Invite code</label>
          <input id="j-code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={20} required className="mono-code" spellCheck={false} />
          {error?.form === "join" && <p className="form__error" role="alert">{error.text}</p>}
          <button className="btn btn--ink" type="submit" disabled={busy !== null}>{busy === "join" ? "Joining…" : "Join the space"}</button>
        </form>
      </div>
    </section>
  );
}
