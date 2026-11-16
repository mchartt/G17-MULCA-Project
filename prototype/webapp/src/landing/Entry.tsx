import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useCallback, useEffect, useState } from "react";
import { AuthForms } from "../account/AuthForms";
import { Home } from "../account/Home";
import { logout, me, type SpaceRef, type User } from "../lib/account";
import { adapterOnline } from "../lib/api";
import { faEye, faHandPointer, faLock, faShieldHalved, faWifi } from "../lib/icons";
import { useReveal } from "../lib/motion";

const NOTICE = [
  { icon: faEye, text: "It reads the messages written in your group's space and in the Discord or Slack channel you link to it, so it can notice what needs coordinating." },
  { icon: faLock, text: "It keeps your email (to log in), your display name and, if you add them, your discipline, skills and weekly hours." },
  { icon: faShieldHalved, text: "Messages are sent to Azure OpenAI to write Cadence's answers and proposals." },
  { icon: faHandPointer, text: "It never scores or ranks people, and nothing in the plan changes until a member confirms it." },
];

/**
 * The way in (UC1): what Cadence reads and keeps, then your account. Logged
 * in, you see your spaces and can start or join one.
 */
export function Entry({ onEnter }: { onEnter: (token: string) => void }) {
  const [online, setOnline] = useState<boolean | null>(null);
  // undefined: still asking the server who is logged in on this browser.
  const [account, setAccount] = useState<{ user: User; spaces: SpaceRef[] } | null | undefined>(undefined);
  const forms = useReveal<HTMLDivElement>();

  const refresh = useCallback(() => me().then(setAccount), []);

  useEffect(() => {
    void adapterOnline().then(setOnline);
    void refresh();
  }, [refresh]);

  const signOut = async () => {
    await logout();
    setAccount(null);
  };

  return (
    <section id="enter" className="entry" aria-labelledby="entry-title">
      <h2 id="entry-title">Open your group's space.</h2>

      {online === false && (
        <div className="offline" role="status">
          <FontAwesomeIcon icon={faWifi} />
          <p>
            This online version shows Cadence's design. Group spaces run on the coordinator server, which is started for the demo
            and for user tests: accounts and spaces work there.
          </p>
        </div>
      )}

      {(
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
        </div>
      )}

      <div ref={forms} className="reveal">
        {account === null && <AuthForms disabled={online === false} onSignedIn={() => void refresh()} />}
        {account && (
          <Home
            user={account.user}
            spaces={account.spaces}
            disabled={online === false}
            onEnter={onEnter}
            onUser={(user) => setAccount({ ...account, user })}
            onLogout={() => void signOut()}
          />
        )}
      </div>
    </section>
  );
}
