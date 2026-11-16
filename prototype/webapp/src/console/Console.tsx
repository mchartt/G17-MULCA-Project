import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { ProfileForm } from "../account/ProfileForm";
import { me, type User } from "../lib/account";
import { faClipboardCheck, faClockRotateLeft, faFileLines, faListOl, faTableColumns } from "../lib/icons";
import { calendarLink, deleteSpace, saveToken } from "../lib/api";
import { SpaceSocket, type SocketStatus } from "../lib/socket";
import type { Answer, CatchUp } from "../lib/types";
import { CatchUpDialog } from "./CatchUpDialog";
import { Chat } from "./Chat";
import { DeleteDialog, Dialog, KickoffDialog, PlanningDialog, ProfileDialog, type Profile } from "./Dialogs";
import { ProjectPanel } from "./ProjectPanel";
import { Sidebar } from "./Sidebar";
import { parseSlash, SLASH_HELP } from "./slash";
import { emptySpace, reduce } from "./space";

const STATUS_TEXT: Partial<Record<SocketStatus, string>> = {
  connecting: "Connecting to your space…",
  closed: "Connection lost. Reconnecting…",
};

/** The three-column console: space on the left, chat in the middle, plan on the right. */
export function Console({ token, onLeave }: { token: string; onLeave: () => void }) {
  const [space, dispatch] = useReducer(reduce, emptySpace);
  const [status, setStatus] = useState<SocketStatus>("connecting");
  const [panelOpen, setPanelOpen] = useState(true);
  const [dialog, setDialog] = useState<"kickoff" | "profile" | "planning" | "delete" | "catchup" | null>(null);
  // Short answers to commands (check-in "on track", task updates), shown above the chat.
  const [notice, setNotice] = useState<string | null>(null);
  const socket = useRef<SpaceSocket | null>(null);
  // The logged-in person (null: a guest of this space, as before accounts).
  const [user, setUser] = useState<User | null>(null);
  const [caught, setCaught] = useState<{ summary: string; catchup: CatchUp | null }>({ summary: "", catchup: null });

  useEffect(() => {
    void me().then((account) => setUser(account?.user ?? null));
  }, []);

  useEffect(() => {
    const s = new SpaceSocket(token, dispatch, setStatus);
    socket.current = s;
    s.open();
    return () => s.close();
  }, [token]);

  const ask = useCallback(async (frame: Parameters<SpaceSocket["ask"]>[0]): Promise<Answer> => {
    if (!socket.current) return { type: "notice", ok: false, text: "Not connected." };
    return socket.current.ask(frame);
  }, []);

  useEffect(() => {
    if (status === "open") void ask({ type: "command", command: "state" });
  }, [status, ask]);

  useEffect(() => {
    if (status === "unauthorized") {
      saveToken(null);
      onLeave();
    }
  }, [status, onLeave]);

  const leave = () => {
    saveToken(null);
    onLeave();
  };

  const kickoff = async (text: string) => {
    const answer = await ask({ type: "command", command: "kickoff", args: { text } });
    if (answer.ok) {
      setDialog(null);
      return null;
    }
    return answer.type === "notice" ? answer.text : "Cadence could not read the assignment.";
  };

  const planning = async (text: string) => {
    const answer = await ask({ type: "command", command: "planning", args: { text } });
    if (answer.ok) {
      setDialog(null);
      return null;
    }
    return answer.type === "notice" ? answer.text : "Cadence could not read the tasks.";
  };

  const checkin = async () => {
    setNotice("Cadence is comparing the plan with the dates…");
    const answer = await ask({ type: "command", command: "checkin" });
    setNotice(answer.type === "notice" ? answer.text : null);
  };

  /** The message box: a slash command runs here and is never posted; anything else goes to the group. */
  const say = (text: string) => {
    const slash = parseSlash(text);
    if (!slash) {
      socket.current?.say(text);
    } else if (slash.kind === "checkin") {
      void checkin();
    } else if (slash.kind === "unknown") {
      setNotice(`/${slash.name} is not a command here. ${SLASH_HELP}`);
    } else if (!slash.tasks) {
      setDialog("planning");
    } else {
      setNotice("Cadence is reading the tasks…");
      void planning(slash.tasks).then(setNotice);
    }
  };

  const catchUp = async () => {
    setCaught({ summary: "", catchup: null });
    setDialog("catchup");
    const answer = await ask({ type: "command", command: "catchup" });
    setCaught(answer.type === "notice" ? { summary: answer.text, catchup: answer.catchup ?? null } : { summary: "No answer.", catchup: null });
  };

  const taskStatus = async (task: string, status: string) => {
    const answer = await ask({ type: "command", command: "task", args: { task, status } });
    if (!answer.ok && answer.type === "notice") setNotice(answer.text);
  };

  const why = async (question: string) => {
    const answer = await ask({ type: "command", command: "why", args: { question } });
    return answer.type === "notice" ? answer.text : "No answer.";
  };

  const removeSpace = async (confirm: string) => {
    const error = await deleteSpace(token, confirm);
    if (!error) leave();
    return error;
  };

  const saveProfile = async (profile: Profile) => {
    const answer = await ask({ type: "command", command: "profile", args: profile });
    return answer.ok ? null : answer.type === "notice" ? answer.text : "Profile not saved.";
  };

  return (
    <div className={`console${panelOpen ? "" : " console--wide"}`}>
      <a href="#composer-input" className="skip">Skip to the message box</a>
      <Sidebar space={space} onProfile={() => setDialog("profile")} onLeave={leave} onDelete={() => setDialog("delete")} />
      <main className="console__main">
        <header className="console__bar">
          <div>
            <h2 className="console__title">Group chat</h2>
            {space.coordinator === "unavailable" && (
              <p className="banner banner--warn" role="status">Cadence is not available right now. The chat still works.</p>
            )}
            {STATUS_TEXT[status] && <p className="banner" role="status">{STATUS_TEXT[status]}</p>}
            {notice && (
              <p className="banner banner--info" role="status">
                {notice} <button className="link-btn" onClick={() => setNotice(null)}>Dismiss</button>
              </p>
            )}
          </div>
          <div className="console__tools">
            <button className="btn btn--soft btn--small" onClick={() => setDialog("kickoff")}><FontAwesomeIcon icon={faFileLines} /> Paste the assignment</button>
            <button className="btn btn--soft btn--small" onClick={() => setDialog("planning")}><FontAwesomeIcon icon={faListOl} /> Plan tasks</button>
            <button className="btn btn--soft btn--small" onClick={() => void checkin()}><FontAwesomeIcon icon={faClipboardCheck} /> Check-in</button>
            <button className="btn btn--soft btn--small" onClick={() => void catchUp()}><FontAwesomeIcon icon={faClockRotateLeft} /> Catch up</button>
            <button className="btn btn--soft btn--small" aria-expanded={panelOpen} aria-controls="plan" onClick={() => setPanelOpen(!panelOpen)}>
              <FontAwesomeIcon icon={faTableColumns} />{" "}
              {panelOpen ? "Hide plan" : "Show plan"}
            </button>
          </div>
        </header>
        <Chat
          space={space}
          disabled={status !== "open"}
          onSay={say}
          onAnswer={(proposalId, click) => ask({ type: "click", proposalId, ...click })}
        />
      </main>
      {panelOpen && (
        <div id="plan" className="console__panel">
          <ProjectPanel
            state={space.state}
            members={space.members}
            names={space.names}
            onKickoff={() => setDialog("kickoff")}
            onRefresh={() => void ask({ type: "command", command: "state" })}
            onTaskStatus={(taskId, value) => void taskStatus(taskId, value)}
            onWhy={why}
            onCalendar={() => calendarLink(token)}
          />
        </div>
      )}
      <KickoffDialog open={dialog === "kickoff"} onClose={() => setDialog(null)} onSend={kickoff} />
      {user ? (
        // Logged in: the profile is the account's, saved once for every space.
        <Dialog open={dialog === "profile"} title="Your profile" onClose={() => setDialog(null)}>
          <ProfileForm user={user} onSaved={setUser} onCancel={() => setDialog(null)} />
        </Dialog>
      ) : (
        <ProfileDialog open={dialog === "profile"} onClose={() => setDialog(null)} onSave={saveProfile} />
      )}
      <CatchUpDialog open={dialog === "catchup"} summary={caught.summary} catchup={caught.catchup} inviteCode={space.group?.inviteCode ?? ""} onClose={() => setDialog(null)} />
      <PlanningDialog open={dialog === "planning"} onClose={() => setDialog(null)} onSend={planning} />
      <DeleteDialog open={dialog === "delete"} spaceName={space.group?.name ?? ""} onClose={() => setDialog(null)} onDelete={removeSpace} />
    </div>
  );
}
