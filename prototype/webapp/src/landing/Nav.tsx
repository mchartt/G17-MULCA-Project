import { useEffect, useState } from "react";

/** Slim translucent bar, Apple-style: dark over the film, light afterwards. */
export function Nav() {
  const [light, setLight] = useState(false);
  useEffect(() => {
    const film = document.querySelector(".film");
    const update = () => setLight(!film || film.getBoundingClientRect().bottom < 60);
    update();
    addEventListener("scroll", update, { passive: true });
    return () => removeEventListener("scroll", update);
  }, []);
  return (
    <header className={`nav${light ? " nav--light" : ""}`}>
      <a className="nav__brand" href="#top">Cadence</a>
      <nav aria-label="Page">
        <a href="#how">How it works</a>
        <a href="#next">What's next</a>
        <a href="#privacy">Privacy</a>
        <a className="nav__cta" href="#enter">Open your space</a>
      </nav>
    </header>
  );
}
