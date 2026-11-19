import { Logo } from "../brand/Logo";

/** Slim translucent bar on the landing and on /login. Links work from both pages. */
export function Nav() {
  return (
    <header className="nav nav--light">
      <a className="nav__brand" href="/#top" aria-label="Cadence, home"><Logo size={26} /></a>
      <nav aria-label="Page">
        <a href="/#how">How it works</a>
        <a href="/login#privacy">Privacy</a>
        <a className="nav__cta" href="/login">Open your space</a>
      </nav>
    </header>
  );
}
