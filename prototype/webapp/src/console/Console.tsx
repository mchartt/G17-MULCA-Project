import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { faFileLines, faTableColumns } from "../lib/icons";
import { saveToken } from "../lib/api";
import { SpaceSocket, type SocketStatus } from "../lib/socket";
import type { Answer } from "../lib/types";
import { Chat } from "./Chat";
import { KickoffDialog, ProfileDialog, type Profile } from "./Dialogs";
import { ProjectPanel } from "./ProjectPanel";
import { Sidebar } from "./Sidebar";
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
  const [dialog, setDialog] = useState<"kickoff" | "profile" | null>(null);
  const socket = useRef<SpaceSocket | null>(null);

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

  const saveProfile = async (profile: Profile) => {
    const answer = await ask({ type: "command", command: "profile", args: profile });
    return answer.ok ? null : answer.type === "notice" ? answer.text : "Profile not saved.";
  };

  return (
    <div className={`console${panelOpen ? "" : " console--wide"}`}>
      <a href="#composer-input" className="skip">Skip to the message box</a>
      <Sidebar space={space} onProfile={() => setDialog("profile")} onLeave={leave} />
      <main className="console__main">
        <header className="console__bar">
          <div>
            <h2 className="console__title">Group chat</h2>
            {space.coordinator === "unavailable" && (
              <p className="banner banner--warn" role="status">Cadence is not available right now. The chat still works.</p>
            )}
            {STATUS_TEXT[status] && <p className="banner" role="status">{STATUS_TEXT[status]}</p>}
          </div>
          <div className="console__tools">
            <button className="btn btn--soft btn--small" onClick={() => setDialog("kickoff")}><FontAwesomeIcon icon={faFileLines} /> Paste the assignment</button>
            <button className="btn btn--soft btn--small" aria-expanded={panelOpen} aria-controls="plan" onClick={() => setPanelOpen(!panelOpen)}>
              <FontAwesomeIcon icon={faTableColumns} />{" "}
              {panelOpen ? "Hide plan" : "Show plan"}
            </button>
          </div>
        </header>
        <Chat
          space={space}
          disabled={status !== "open"}
          onSay={(text) => socket.current?.say(text)}
          onAnswer={(proposalId, click) => ask({ type: "click", proposalId, ...click })}
        />
      </main>
      {panelOpen && (
        <div id="plan" className="console__panel">
          <ProjectPanel
            state={space.state}
            members={space.members}
            onKickoff={() => setDialog("kickoff")}
            onRefresh={() => void ask({ type: "command", command: "state" })}
          />
        </div>
      )}
      <KickoffDialog open={dialog === "kickoff"} onClose={() => setDialog(null)} onSend={kickoff} />
      <ProfileDialog open={dialog === "profile"} onClose={() => setDialog(null)} onSave={saveProfile} />
    </div>
  );
}
