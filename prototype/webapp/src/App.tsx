import { useCallback, useState } from "react";
import { Console } from "./console/Console";
import { savedToken } from "./lib/api";
import { Landing } from "./landing/Landing";
import { Preview } from "./preview/Preview";

/**
 * Two places, the landing (film, entry) and the console of your space, plus
 * the preview screens under /preview (sample data, no space needed).
 */
export function App() {
  const [token, setToken] = useState<string | null>(() => savedToken());

  const enter = useCallback((t: string) => {
    history.pushState(null, "", "/space");
    setToken(t);
    scrollTo(0, 0);
  }, []);

  const leave = useCallback(() => {
    history.pushState(null, "", "/");
    setToken(null);
  }, []);

  if (location.pathname.startsWith("/preview")) return <Preview />;
  return token ? <Console token={token} onLeave={leave} /> : <Landing onEnter={enter} />;
}
