import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useCallback, useEffect, useState } from "react";
import { Nav } from "../landing/Nav";
import { logout, me, type SpaceRef, type User } from "../lib/account";
import { adapterOnline } from "../lib/api";
import { faEye, faHandPointer, faLock, faShieldHalved, faWifi } from "../lib/icons";
import { codeInAddress } from "../lib/invite";
import { AuthForms } from "./AuthForms";
import { Home } from "./Home";
import { profileDone, Welcome } from "./Welcome";

const NOTICE = [
  { icon: faEye, text: "It reads the messages written in your group's space and in the Discord or Slack channel you link to it, so it can notice what needs coordinating." },
  { icon: faLock, text: "It keeps your email (to log in), your display name and, if you add them, your discipline, skills and weekly hours." },
  { icon: faShieldHalved, text: "Messages, and the brief or documents you give when creating a project, are sent to Azure OpenAI to write Cadence's answers and proposals. Uploaded files are read, not kept." },
  { icon: faHandPointer, text: "It never scores or ranks people, and nothing in the plan changes until a member confirms it." },
];

/** What Cadence reads and keeps. Shown next to the forms, before anyone signs up. */
function PrivacyNotice() {
  return (
    <div id="privacy" className="notice">
      <h2>What Cadence reads and keeps</h2>
      <ul>
        {NOTICE.map((n) => (
          <li key={n.text}>
            <span className="notice__icon"><FontAwesomeIcon icon={n.icon} /></span>
            {n.text}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The way in (UC1), on its own page (/login): log in or create an account,
 * with the privacy notice beside it. Logged in, you see your spaces and can
 * start or join one; an invite link (/login?code=...) fills in the code.
 */
export function LoginPage({ onEnter }: { onEnter: (token: string) => void }) {
  const [online, setOnline] = useState<boolean | null>(null);
  // undefined: still asking the server who is logged in on this browser.
  const [account, setAccount] = useState<{ user: User; spaces: SpaceRef[] } | null | undefined>(undefined);

  // An invite link (/login?code=...) brings a teammate here: the page says so.
  const invited = codeInAddress() !== "";

  // The guided setup, shown to a new account (empty profile, no space) until finished or skipped.
  const [guided, setGuided] = useState<boolean | null>(null);
  const refresh = useCallback(
    () =>
      me().then((found) => {
        setAccount(found);
        setGuided((before) => before ?? (found ? !profileDone(found.user) && found.spaces.length === 0 : null));
      }),
    [],
  );

  useEffect(() => {
    void adapterOnline().then(setOnline);
    void refresh();
  }, [refresh]);

  const signOut = async () => {
    await logout();
    setAccount(null);
    setGuided(null);
  };

  if (account && guided) {
    return (
      <div className="login-page login-page--welcome">
        <Nav />
        <main className="entry entry--welcome">
          <Welcome
            user={account.user}
            start="name"
            disabled={online === false}
            onUser={(user) => setAccount({ ...account, user })}
            onEnter={onEnter}
            onSkip={() => setGuided(false)}
          />
        </main>
      </div>
    );
  }

  return (
    <div className="login-page">
      <Nav />
      <main id="enter" className="entry" aria-labelledby="entry-title">
        <h1 id="entry-title">{account ? "Your spaces." : invited ? "Join your group's space." : "Open your group's space."}</h1>
        {invited && !account && <p className="entry__lead">You have an invite. Create an account or log in, and the code is already filled in.</p>}

        {online === false && (
          <div className="offline" role="status">
            <FontAwesomeIcon icon={faWifi} />
            <p>
              This online version shows Cadence's design. Group spaces run on the coordinator server, which is started for the demo
              and for user tests: accounts and spaces work there.
            </p>
          </div>
        )}

        <div className="entry__layout">
          <div className="entry__main">
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
          <PrivacyNotice />
        </div>
      </main>
    </div>
  );
}
