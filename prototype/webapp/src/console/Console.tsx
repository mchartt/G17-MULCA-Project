import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { ProfileForm } from "../account/ProfileForm";
import { me, type User } from "../lib/account";
import { faClipboardCheck, faClockRotateLeft, faFileLines, faListOl, faTableColumns } from "../lib/icons";
import { ADAPTER_URL, calendarLink, deleteSpace, saveToken } from "../lib/api";
import { readDocument } from "../lib/documents";
import { parseSlash } from "../lib/slash";
import { SpaceSocket, type SocketStatus } from "../lib/socket";
import type { Answer, CatchUp } from "../lib/types";
import { CatchUpDialog } from "./CatchUpDialog";
import { Chat } from "./Chat";
import { FirstSteps } from "./FirstSteps";
import { DeleteDialog, Dialog, KickoffDialog, ProfileDialog, type Profile } from "./Dialogs";
import { AgendaDialog, MilestonesDialog, PlanningDialog, TaskRegisterDialog } from "./PlanDialogs";
import type { MilestoneEdit, NewTask, TaskEdit } from "./plan";
import { ProjectPanel } from "./ProjectPanel";
import { Sidebar } from "./Sidebar";
import { emptySpace, nameOf, reduce } from "./space";

const STATUS_TEXT: Partial<Record<SocketStatus, string>> = {
  connecting: "Connecting to your space…",
  closed: "Connection lost. Reconnecting…",
};

/** The three-column console: space on the left, chat in the middle, plan on the right. */
export function Console({ token, onLeave }: { token: string; onLeave: () => void }) {
  const [space, dispatch] = useReducer(reduce, emptySpace);
  const [status, setStatus] = useState<SocketStatus>("connecting");
  const [panelOpen, setPanelOpen] = useState(true);
  const [dialog, setDialog] = useState<"kickoff" | "profile" | "planning" | "delete" | "catchup" | "tasks" | "agenda" | "milestones" | null>(null);
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

  // Render's free plan stops a server that gets no request for 15 minutes,
  // and an open chat sends none by itself. A small request every few minutes
  // while someone has the space open keeps it awake.
  useEffect(() => {
    const ping = () => {
      if (document.visibilityState === "visible") void fetch(`${ADAPTER_URL}/api/health`, { cache: "no-store" }).catch(() => undefined);
    };
    const timer = window.setInterval(ping, 4 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, []);

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

  /** The planning list: owners the group chose are kept, Cadence suggests the others. */
  const planningList = async (items: NewTask[]) => {
    const answer = await ask({
      type: "command",
      command: "planning",
      args: { items: items.map((i) => ({ title: i.title, owner_id: i.owner, due_date: i.due })) },
    });
    if (answer.ok) {
      setDialog(null);
      return null;
    }
    return answer.type === "notice" ? answer.text : "Cadence could not read the tasks.";
  };

  /** A member changes a task by hand (done, owner, date, removal). A refusal is shown above the chat. */
  const editTask = async (task: string, edit: TaskEdit) => {
    const args: Record<string, unknown> = { task };
    if (edit.status !== undefined) args.status = edit.status;
    if (edit.owner !== undefined) args.owner = edit.owner ?? "";
    if (edit.due !== undefined) args.due = edit.due ?? "";
    if (edit.title !== undefined) args.title = edit.title;
    if (edit.remove) args.remove = true;
    const answer = await ask({ type: "command", command: "task", args });
    if (!answer.ok && answer.type === "notice") setNotice(answer.text);
  };

  const addTask = async (task: NewTask) => {
    const answer = await ask({ type: "command", command: "task", args: { add: task.title, owner: task.owner ?? "", due: task.due ?? "" } });
    return answer.ok ? null : answer.type === "notice" ? answer.text : "The task was not added.";
  };

  const editMilestone = async (edit: MilestoneEdit) => {
    const args: Record<string, unknown> = "add" in edit ? { add: edit.add, due: edit.due ?? "" } : { milestone: edit.milestone };
    if (!("add" in edit)) {
      if (edit.title !== undefined) args.title = edit.title;
      if (edit.due !== undefined) args.due = edit.due ?? "";
      if (edit.remove) args.remove = true;
    }
    const answer = await ask({ type: "command", command: "milestone", args });
    return answer.ok ? null : answer.type === "notice" ? answer.text : "The milestone was not changed.";
  };

  const checkin = async () => {
    setNotice("Cadence is comparing the plan with the dates…");
    const answer = await ask({ type: "command", command: "checkin" });
    setNotice(answer.type === "notice" ? answer.text : null);
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

  /** The language of everything Cadence writes for this group ("" = it follows the chat). */
  const setLanguage = async (language: string) => {
    const answer = await ask({ type: "command", command: "language", args: { language: language || "auto" } });
    if (answer.type === "notice") setNotice(answer.text);
  };

  /** A member rewrites the goal and deliverables: it becomes a card to confirm in the chat. */
  const editCharter = async (goal: string, deliverables: string[]) => {
    const answer = await ask({ type: "command", command: "charter", args: { goal, deliverables } });
    if (answer.ok) {
      setNotice("Your change is a card in the chat: it is saved when a member confirms it.");
      return null;
    }
    return answer.type === "notice" ? answer.text : "The goal was not changed.";
  };

  // A "/..." line typed in the chat (lib/slash.ts): the same actions as the buttons.
  const runSlash = async (text: string) => {
    const slash = parseSlash(text);
    if (!slash) return;
    if (slash.kind === "say") return setNotice(slash.text);
    if (slash.kind === "task") return void taskStatus(slash.task, slash.status);
    if (slash.kind === "addtask") return setNotice((await addTask({ title: slash.title, owner: null, due: null })) ?? `Task added: “${slash.title}”.`);
    switch (slash.name) {
      case "kickoff":
        if (!slash.rest) return setDialog("kickoff");
        setNotice("Cadence is reading the assignment…");
        return setNotice(await kickoff(slash.rest));
      case "planning":
        if (!slash.rest) return setDialog("planning");
        setNotice("Cadence is planning the tasks…");
        return setNotice(await planning(slash.rest.split(/[\n;]/).map((t) => t.trim()).filter(Boolean).join("\n")));
      case "checkin":
        return void checkin();
      case "catchup":
        return void catchUp();
      case "why":
        return setNotice(await why(slash.rest));
      case "ask": {
        // Answered from what is saved (plan, dates, decisions), with its source.
        const answer = await ask({ type: "command", command: "ask", args: { question: slash.rest } });
        return setNotice(answer.type === "notice" ? answer.text : "No answer.");
      }
      case "plan":
        return setPanelOpen(true);
      case "profile":
        return setDialog("profile");
      case "language":
        return void setLanguage(slash.rest.toLowerCase());
    }
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
          <h2 className="console__title">Group chat</h2>
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
          {(space.coordinator === "unavailable" || STATUS_TEXT[status] || notice) && (
            <div className="console__notices">
              {space.coordinator === "unavailable" && (
                <p className="banner banner--warn" role="status">Cadence is not available right now. The chat still works.</p>
              )}
              {STATUS_TEXT[status] && <p className="banner" role="status">{STATUS_TEXT[status]}</p>}
              {notice && (
                <p className="banner banner--info" role="status">
                  <span>{notice}</span> <button className="link-btn" onClick={() => setNotice(null)}>Dismiss</button>
                </p>
              )}
            </div>
          )}
        </header>
        <FirstSteps
          state={space.state}
          me={space.me?.id ?? null}
          onProfile={() => setDialog("profile")}
          onKickoff={() => setDialog("kickoff")}
          onPlanning={() => setDialog("planning")}
        />
        <Chat
          space={space}
          disabled={status !== "open"}
          onCommand={(text) => void runSlash(text)} onSay={(text) => socket.current?.say(text)}
          onAnswer={(proposalId, click) => ask({ type: "click", proposalId, ...click })}
        />
      </main>
      {panelOpen && (
        <div id="plan" className="console__panel">
          <ProjectPanel
            state={space.state}
            members={space.members}
            names={space.names}
            me={space.me?.id ?? null}
            onProfile={() => setDialog("profile")}
            onLanguage={(language) => void setLanguage(language)}
            onCharter={editCharter}
            onKickoff={() => setDialog("kickoff")}
            onRefresh={() => void ask({ type: "command", command: "state" })}
            onTask={(taskId, edit) => void editTask(taskId, edit)}
            onOpen={setDialog}
            onWhy={why}
            onCalendar={() => calendarLink(token)}
          />
        </div>
      )}
      <KickoffDialog open={dialog === "kickoff"} onClose={() => setDialog(null)} onSend={kickoff} onRead={(file) => readDocument(token, file)} />
      {user ? (
        // Logged in: the profile is the account's, saved once for every space.
        <Dialog open={dialog === "profile"} title="Your profile" onClose={() => setDialog(null)}>
          <ProfileForm user={user} onSaved={setUser} onCancel={() => setDialog(null)} />
        </Dialog>
      ) : (
        <ProfileDialog open={dialog === "profile"} onClose={() => setDialog(null)} onSave={saveProfile} />
      )}
      <CatchUpDialog open={dialog === "catchup"} summary={caught.summary} catchup={caught.catchup} inviteCode={space.group?.inviteCode ?? ""} onClose={() => setDialog(null)} />
      <PlanningDialog open={dialog === "planning"} members={space.members} onClose={() => setDialog(null)} onSend={planningList} />
      <TaskRegisterDialog
        open={dialog === "tasks"}
        tasks={space.state?.tasks ?? []}
        members={space.members}
        me={space.me?.id ?? null}
        nameOf={(id) => nameOf(id, space)}
        onTask={(taskId, edit) => void editTask(taskId, edit)}
        onAdd={addTask}
        onClose={() => setDialog(null)}
      />
      <AgendaDialog
        open={dialog === "agenda"}
        tasks={space.state?.tasks ?? []}
        milestones={space.state?.milestones ?? []}
        members={space.members}
        nameOf={(id) => nameOf(id, space)}
        onTask={(taskId, edit) => void editTask(taskId, edit)}
        onClose={() => setDialog(null)}
      />
      <MilestonesDialog open={dialog === "milestones"} milestones={space.state?.milestones ?? []} onMilestone={editMilestone} onClose={() => setDialog(null)} />
      <DeleteDialog open={dialog === "delete"} spaceName={space.group?.name ?? ""} onClose={() => setDialog(null)} onDelete={removeSpace} />
    </div>
  );
}
