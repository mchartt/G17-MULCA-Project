import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useCallback, useEffect, useState } from "react";
import { Nav } from "../landing/Nav";
import { logout, me, type SpaceRef, type User } from "../lib/account";
import { adapterOnline } from "../lib/api";
import { faEye, faHandPointer, faLock, faShieldHalved, faWifi } from "../lib/icons";
import { codeInAddress } from "../lib/invite";
import { AuthForms } from "./AuthForms";
import { Home } from "./Home";
import { ProjectDesk } from "./ProjectDesk";
import { profileDone, Welcome } from "./Welcome";

const NOTICE = [
  { icon: faEye, text: "It reads the messages written in your group's space and in the Discord or Slack channel you link to it, so it can notice what needs coordinating." },
  { icon: faLock, text: "It keeps your email (to log in), your display name and, if you add them, your discipline, skills and weekly hours." },
  { icon: faShieldHalved, text: "Messages, and the brief or documents you give when creating a project, are sent to Azure OpenAI to write Cadence's answers and proposals. Uploaded files are read, not kept." },
  { icon: faHandPointer, text: "It never scores or ranks people, and nothing in the plan changes until a member confirms it." },
];

/** What Cadence reads and keeps: beside the sign-up form, and behind a button on the home. */
export function PrivacyNotice({ id, heading = true }: { id?: string; heading?: boolean }) {
  return (
    <div id={id} className="notice">
      {heading && <h2>What Cadence reads and keeps</h2>}
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

/** Beside the sign-up form: a group at work, one line on what Cadence does, and the privacy notice. */
function BrandPanel() {
  return (
    <aside className="brandpanel" aria-labelledby="brandpanel-title">
      <img src="/brand/group-at-laptop.webp" width={1672} height={941} alt="Three students around a laptop, working on their group project." decoding="async" />
      <h2 id="brandpanel-title">Cadence connects your tasks, your plan and your decisions.</h2>
      <PrivacyNotice id="privacy" />
    </aside>
  );
}

function Offline() {
  return (
    <div className="offline" role="status">
      <FontAwesomeIcon icon={faWifi} />
      <p>
        This online version shows Cadence's design. Group spaces run on the coordinator server, which is started for the demo
        and for user tests: accounts and spaces work there.
      </p>
    </div>
  );
}

type Props = {
  /** /login (the home) or /login/new (the setup desk). */
  path: string;
  onNavigate: (path: string) => void;
  onEnter: (token: string) => void;
};

/**
 * The way in (UC1), on its own page (/login): log in or create an account,
 * with the privacy notice beside it. Logged in, the home lists your projects
 * and lets you join one with a code; a new project is set up on its own page,
 * the desk (/login/new). An invite link (/login?code=...) fills in the code.
 */
export function LoginPage({ path, onNavigate, onEnter }: Props) {
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

  // The setup desk: the guided setup is over once someone chooses to create a project.
  const openDesk = () => {
    setGuided(false);
    onNavigate("/login/new");
  };
  const offline = online === false;

  if (account && path.startsWith("/login/new")) {
    return (
      <div className="login-page login-page--fit">
        <Nav />
        <main className="desk-page" aria-labelledby="desk-title">
          {offline && <Offline />}
          <ProjectDesk disabled={offline} onEnter={onEnter} onBack={() => onNavigate("/login")} />
        </main>
      </div>
    );
  }

  if (account && guided) {
    return (
      <div className="login-page login-page--welcome">
        <Nav />
        <main className="entry entry--welcome">
          <Welcome
            user={account.user}
            start="name"
            disabled={offline}
            onUser={(user) => setAccount({ ...account, user })}
            onEnter={onEnter}
            onCreate={openDesk}
            onSkip={() => setGuided(false)}
          />
        </main>
      </div>
    );
  }

  if (account) {
    return (
      <div className="login-page login-page--fit">
        <Nav />
        <main className="home-page" aria-labelledby="home-title">
          {offline && <Offline />}
          <Home
            user={account.user}
            spaces={account.spaces}
            disabled={offline}
            onEnter={onEnter}
            onNew={openDesk}
            onUser={(user) => setAccount({ ...account, user })}
            onLogout={() => void signOut()}
          />
        </main>
      </div>
    );
  }

  return (
    <div className="login-page login-page--fit">
      <Nav />
      <main id="enter" className="entry entry--signin" aria-labelledby="entry-title">
        <div className="entry__main">
          <h1 id="entry-title">{invited ? "Join your group's space." : "Open your group's space."}</h1>
          {invited && <p className="entry__lead">You have an invite. Create an account or log in, and the code is already filled in.</p>}
          {offline && <Offline />}
          {account === null && <AuthForms disabled={offline} onSignedIn={() => void refresh()} />}
        </div>
        <BrandPanel />
      </main>
    </div>
  );
}
