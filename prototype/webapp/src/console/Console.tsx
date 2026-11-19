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
import { AskMenu } from "./AskMenu";
import { CatchUpDialog } from "./CatchUpDialog";
import { Chat } from "./Chat";
import { FirstSteps } from "./FirstSteps";
import { DeleteDialog, Dialog, KickoffDialog, ProfileDialog, type Profile } from "./Dialogs";
import { AgendaDialog, MilestonesDialog, PlanningDialog, TaskRegisterDialog } from "./PlanDialogs";
import type { MilestoneEdit, NewTask, TaskEdit } from "./plan";
import { todayIso, todayView } from "./plan";
import { NewMilestoneDialog, NewTaskDialog, TodayDialog } from "./QuickDialogs";
import { ProjectPanel } from "./ProjectPanel";
import { DependenciesPage, MilestonesPage, ReflectionPage } from "./Pages";
import { Sidebar, type View } from "./Sidebar";
import { emptySpace, nameOf, reduce } from "./space";

const PAGE_TITLES: Record<View, string> = { chat: "Group chat", dependencies: "Dependencies", milestones: "Milestones", reflection: "Reflection" };

const STATUS_TEXT: Partial<Record<SocketStatus, string>> = {
  connecting: "Connecting to your space…",
  closed: "Connection lost. Reconnecting…",
};

/**
 * The console, chat first: the space on the left, the group chat in the
 * middle. The plan is memory, not the reason to open Cadence, so it starts
 * closed and opens beside the chat on request ("Plan"). The on-demand
 * actions live behind one "Ask Cadence" menu (tutor feedback, 18 Nov:
 * "you can start without showing the plan"; "so much happening at once").
 */
export function Console({ token, onLeave }: { token: string; onLeave: () => void }) {
  const [space, dispatch] = useReducer(reduce, emptySpace);
  const [status, setStatus] = useState<SocketStatus>("connecting");
  const [panelOpen, setPanelOpen] = useState(false);
  // The page beside the chat: the chat is where a space opens.
  const [view, setView] = useState<View>("chat");
  const [dialog, setDialog] = useState<"kickoff" | "profile" | "planning" | "delete" | "catchup" | "tasks" | "agenda" | "milestones" | "newtask" | "newmilestone" | "today" | null>(null);
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
    const args: Record<string, unknown> = { add: task.title, owner: task.owner ?? "", due: task.due ?? "" };
    if (task.description) args.description = task.description;
    if (task.waitsOn?.length) args.depends_on = task.waitsOn;
    const answer = await ask({ type: "command", command: "task", args });
    return answer.ok ? null : answer.type === "notice" ? answer.text : "The task was not added.";
  };

  /** The "New task" popup: it closes only when the server accepted the task. */
  const createTask = async (task: NewTask) => {
    const error = await addTask(task);
    if (!error) {
      setDialog(null);
      setNotice(`Task added: “${task.title}”.`);
    }
    return error;
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

  /** The "New milestone" popup: it closes only when the server accepted the milestone. */
  const createMilestone = async (edit: MilestoneEdit) => {
    const error = await editMilestone(edit);
    if (!error && "add" in edit) {
      setDialog(null);
      setNotice(`Milestone added: “${edit.add}”.`);
    }
    return error;
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
      <Sidebar space={space} view={view} onView={setView} onProfile={() => setDialog("profile")} onLeave={leave} onDelete={() => setDialog("delete")} onNew={(what) => setDialog(what === "task" ? "newtask" : "newmilestone")} />
      <main className="console__main">
        <header className="console__bar">
          <h2 className="console__title">{PAGE_TITLES[view]}</h2>
          <div className="console__tools">
            {(space.state?.tasks?.length ?? 0) > 0 && <TodayChip tasks={space.state?.tasks ?? []} onOpen={() => setDialog("today")} />}
            <AskMenu
              items={[
                { key: "kickoff", label: "Paste the assignment", about: "Cadence proposes the goal, deliverables and milestones.", icon: faFileLines, run: () => setDialog("kickoff") },
                { key: "planning", label: "Plan tasks", about: "List the tasks; Cadence suggests who could take each.", icon: faListOl, run: () => setDialog("planning") },
                { key: "checkin", label: "Check-in", about: "Compare the plan with the dates and see what slips.", icon: faClipboardCheck, run: () => void checkin() },
                { key: "catchup", label: "Catch up", about: "What changed while you were away.", icon: faClockRotateLeft, run: () => void catchUp() },
              ]}
            />
            <button className="btn btn--soft btn--small" aria-expanded={panelOpen} aria-controls="plan" onClick={() => setPanelOpen(!panelOpen)}>
              <FontAwesomeIcon icon={faTableColumns} /> Plan
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
        {view === "chat" && (
          <>
            <FirstSteps
              state={space.state}
              me={space.me?.id ?? null}
              memberCount={space.members.length}
              inviteCode={space.group?.inviteCode ?? ""}
              onProfile={() => setDialog("profile")}
            />
            <Chat
              space={space}
              disabled={status !== "open"}
              onCommand={(text) => void runSlash(text)} onSay={(text) => socket.current?.say(text)}
              onAnswer={(proposalId, click) => ask({ type: "click", proposalId, ...click })}
            />
          </>
        )}
        {view === "dependencies" && <DependenciesPage tasks={space.state?.tasks ?? []} onNew={() => setDialog("newtask")} />}
        {view === "milestones" && <MilestonesPage milestones={space.state?.milestones ?? []} today={todayIso()} onMilestone={editMilestone} onNew={() => setDialog("newmilestone")} />}
        {view === "reflection" && <ReflectionPage state={space.state} today={todayIso()} />}
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
      <NewTaskDialog open={dialog === "newtask"} tasks={space.state?.tasks ?? []} members={space.members} onClose={() => setDialog(null)} onCreate={createTask} />
      <NewMilestoneDialog open={dialog === "newmilestone"} onClose={() => setDialog(null)} onCreate={createMilestone} />
      <TodayDialog open={dialog === "today"} today={todayIso()} tasks={space.state?.tasks ?? []} nameOf={(id) => nameOf(id, space)} onTask={(taskId, edit) => void editTask(taskId, edit)} onClose={() => setDialog(null)} />
      <DeleteDialog open={dialog === "delete"} spaceName={space.group?.name ?? ""} onClose={() => setDialog(null)} onDelete={removeSpace} />
    </div>
  );
}

/** One quiet line above the chat: how many tasks are due today or late. It only opens the popup. */
function TodayChip({ tasks, onOpen }: { tasks: NonNullable<Parameters<typeof todayView>[0]>; onOpen: () => void }) {
  const view = todayView(tasks, todayIso());
  const label =
    view.late.length + view.today.length === 0
      ? "Today: nothing due"
      : [view.today.length > 0 && `${view.today.length} due`, view.late.length > 0 && `${view.late.length} late`].filter(Boolean).join(", ").replace(/^/, "Today: ");
  return (
    <button className="chip chip--today" onClick={onOpen}>{label}</button>
  );
}
