import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useState, type FormEvent } from "react";
import { login, register, type User } from "../lib/account";
import { ApiError } from "../lib/api";
import { faArrowRight } from "../lib/icons";

type Props = { disabled: boolean; onSignedIn: (user: User) => void };

/** Create an account or log in. The privacy notice sits beside it, in LoginPage. */
export function AuthForms({ disabled, onSignedIn }: Props) {
  const [mode, setMode] = useState<"register" | "login">("register");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const creating = mode === "register";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (creating && !agreed) {
      setError("Read what Cadence reads and keeps, then tick the box.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSignedIn(creating ? await register(email, password, name) : await login(email, password));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel-card form auth" onSubmit={submit}>
      <div className="auth__tabs" role="tablist" aria-label="Account">
        <button type="button" role="tab" aria-selected={creating} className="auth__tab" onClick={() => { setMode("register"); setError(null); }}>Create an account</button>
        <button type="button" role="tab" aria-selected={!creating} className="auth__tab" onClick={() => { setMode("login"); setError(null); }}>Log in</button>
      </div>

      {creating && (
        <>
          <label htmlFor="a-name">Your name, as your group will see it</label>
          <input id="a-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required autoComplete="name" />
        </>
      )}
      <label htmlFor="a-email">Email</label>
      <input id="a-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} required autoComplete="email" />
      <label htmlFor="a-password">Password{creating ? " (at least 8 characters)" : ""}</label>
      <input id="a-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} minLength={creating ? 8 : 1} maxLength={200} required autoComplete={creating ? "new-password" : "current-password"} />

      {creating && (
        <label className="check">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          I have read this and I agree
        </label>
      )}
      {error && <p className="form__error" role="alert">{error}</p>}
      <button className="btn btn--primary" type="submit" disabled={disabled || busy}>
        {busy ? "One moment…" : creating ? "Create my account" : "Log in"} <FontAwesomeIcon icon={faArrowRight} />
      </button>
    </form>
  );
}
