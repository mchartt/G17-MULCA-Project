import { useCallback, useState } from "react";
import { Console } from "./console/Console";
import { savedToken } from "./lib/api";
import { Landing } from "./landing/Landing";

/** Two places only: the landing (film, entry) and the console of your space. */
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

  return token ? <Console token={token} onLeave={leave} /> : <Landing onEnter={enter} />;
}
