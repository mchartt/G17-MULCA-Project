import { useCallback, useEffect, useState } from "react";
import { LoginPage } from "./account/LoginPage";
import { Console } from "./console/Console";
import { savedToken } from "./lib/api";
import { Landing } from "./landing/Landing";
import { Preview } from "./preview/Preview";

/** Moves to another page of the app without reloading it. */
function go(path: string) {
  history.pushState(null, "", path);
  scrollTo(0, 0);
}

/**
 * Old invite links point to "/?code=...": they now open the login page, where
 * the code is read (account/Home.tsx).
 */
function redirectInvite() {
  if (location.pathname === "/" && new URLSearchParams(location.search).has("code")) {
    history.replaceState(null, "", `/login${location.search}`);
  }
}

/**
 * The pages of the app:
 *   /          landing (film, how it works, link to /login)
 *   /login     log in or create an account, then your projects
 *   /login/new the setup desk: name, brief and documents of a new project
 *   /space     the console of the space you opened
 *   /preview/  preview screens with sample data, no space needed
 */
export function App() {
  const [token, setToken] = useState<string | null>(() => savedToken());
  const [path, setPath] = useState(() => {
    redirectInvite();
    return location.pathname;
  });

  // The browser's back and forward buttons change the page too.
  useEffect(() => {
    const onPop = () => setPath(location.pathname);
    addEventListener("popstate", onPop);
    return () => removeEventListener("popstate", onPop);
  }, []);

  const enter = useCallback((t: string) => {
    go("/space");
    setPath("/space");
    setToken(t);
  }, []);

  // Pages inside /login (the home and the setup desk) move without reloading.
  const navigate = useCallback((to: string) => {
    go(to);
    setPath(to);
  }, []);

  const leave = useCallback(() => {
    go("/login");
    setPath("/login");
    setToken(null);
  }, []);

  if (path.startsWith("/preview")) return <Preview />;
  if (token) return <Console token={token} onLeave={leave} />;
  if (path.startsWith("/login")) return <LoginPage path={path} onNavigate={navigate} onEnter={enter} />;
  return <Landing />;
}
