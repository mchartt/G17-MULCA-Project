// Shapes exchanged with the web adapter (mulca_discord/web/app.py) and, inside
// them, with MUCA-Server's coordinator events (muca_server/protocol/coordinator.py).

export type Person = { id: number; name: string };
export type Group = { id: number; name: string; inviteCode: string };

export type ChatMessage = {
  id: number;
  author: Person | null; // null = written by the coordinator
  channel: "web" | "discord" | "slack" | "calendar";
  text: string;
  ts: number;
};

export type ProposalStatus = "pending" | "applied" | "rejected" | "expired" | "snoozed";

/** A button on a card, as the server expects it (muca_server/protocol/coordinator.py). */
export type CardAction = "confirm" | "reject" | "take" | "choose" | "not_now" | "helpful";
export type Click = { action: CardAction; option?: number };
export type CommandName = "profile" | "kickoff" | "state" | "planning" | "checkin" | "task" | "why" | "ask" | "catchup" | "language" | "charter" | "milestone" | "approach" | "document" | "reflection" | "me";

/**
 * A member's id. Web members have small numbers. In a linked group a card can
 * name a Discord or Slack member: their ids are too large for a JavaScript
 * number, so the adapter sends them as text (web/hub.py browser_safe).
 */
export type MemberId = number | string;
/** id -> name for the whole group, sent with every card and state. */
export type Names = Record<string, string>;

/** What a member missed in the group's other channels (command "catchup"). */
export type CatchUp = {
  since: number;
  until: number;
  linked: boolean;
  decisions: { question: string; choice: string; reason?: string; decided_by?: MemberId; decided_at?: number }[];
  elsewhere: CatchUpChannel[];
  /** This channel's own chat since the last visit (20/11: the group chat is part of the catch-up). */
  here?: CatchUpChannel;
  tasks_done?: CatchUpTask[];
  tasks_added?: CatchUpTask[];
  /** "In brief": the topics of those messages, summed up by Cadence (only with args.recap). */
  topics?: { title: string; summary: string }[];
  /** "In brief" (args.recap): what the messages since then said, summed up by Cadence from them only. */
  recap?: { overview: string; topics: { title: string; summary: string }[]; open: string[] };
};
export type CatchUpChannel = { channel: string; total: number; messages: { speaker: string; text: string; at: number }[] };
export type CatchUpTask = { task_id: string; title: string; owner_id?: MemberId | null; at?: number | null };

/** The week's reflection (command "reflection"): facts from the plan and the chat, topics from Cadence. Group-level only. */
export type Reflection = {
  week: string;
  until: string;
  current: boolean;
  done: { task_id: string; title: string; owner_id?: MemberId | null; at?: number }[];
  added: { task_id: string; title: string; owner_id?: MemberId | null; due_date?: string | null }[];
  decisions: { decision_id: string; question: string; choice: string; reason?: string; at: number }[];
  slipped: { task_id: string; title: string; owner_id?: MemberId | null; due_date?: string | null }[];
  upcoming: { milestone_id: string; title: string; due_date: string }[];
  talk: { channel: string; messages: number }[];
  /** The week day by day (Monday first): the group's messages and tasks done, counts only. */
  days?: { day: string; messages: number; done: number }[];
  progress: { done: number; total: number };
  topics: { title: string; summary: string }[];
};

/** A document Cadence reads as project context; its text stays on the server. */
export type ProjectDocument = { document_id: string; name: string; chars: number; added_by?: MemberId | null; added_at: number };

/** Why a proactive card exists (M3): strategy, topic, and the messages behind it. */
export type ProactiveContext = {
  strategy_id: string;
  topic: string;
  evidence: { speaker: string; text: string; at_ms: number }[];
};

export type Milestone = { milestone_id?: string; title: string; due_date?: string | null; status?: string };

export type Proposal = {
  proposal_id: string;
  kind: string;
  status: ProposalStatus;
  rationale?: string;
  expires_at?: number | null;
  /** Who answered the card (applied, rejected, snoozed), so the outcome says who. */
  resolved_by?: MemberId | null;
  names?: Names;
  payload: {
    goal?: string;
    deliverables?: string[];
    milestones?: Milestone[];
    // M3 proactive cards (task_owner, delegation, decision)
    context?: ProactiveContext;
    title?: string;
    owner_id?: MemberId | null;
    due_date?: string | null;
    return_to?: string;
    question?: string;
    options?: { label: string; argument?: string }[];
    // M4 cards (plan, checkin, blocker)
    items?: { title: string; owner_id?: MemberId | null; reason?: string; due_date?: string | null }[];
    findings?: string[];
    /** A check-in a member asked for in words ("Cadence, segna X al 50%"): titled as an update. */
    requested?: boolean;
    helper_id?: MemberId | null;
    // CS7 v2 (blocker) and K3 (revisit)
    certainty?: "blocked" | "possible";
    depends_on_title?: string;
    /** CS7: the member the chat named as the one who delivers the work it waits on (owner of that new task). */
    depends_on_owner_id?: MemberId | null;
    ways_forward?: string[];
    choice?: string;
    reason?: string;
    new_point?: string;
    [key: string]: unknown;
  };
};

export type ProjectState = {
  charter?: { goal: string; deliverables?: string[]; confirmed_by?: MemberId } | null;
  names?: Names;
  milestones?: Milestone[];
  members?: { member_id?: MemberId; display_name: string; discipline?: string; skills?: string[]; weekly_hours?: number | null; background?: string }[];
  /** The language the group chose for Cadence's texts: "en", "it", or "" (it follows the chat). */
  language?: string;
  tasks?: {
    task_id?: string;
    title: string;
    status: string;
    owner_id?: MemberId | null;
    due_date?: string | null;
    description?: string;
    depends_on?: string[];
    /** Where each link came from (task it waits on -> "card <id>: <chat line>", "by hand (<member>)"); missing = not known. */
    dependency_sources?: Record<string, string>;
    /** 0-100, set by a member; 100 when done. */
    progress?: number;
    created_at?: number | null;
    done_at?: number | null;
  }[];
  documents?: ProjectDocument[];
  /** decided_by / decided_at: shown when the server sends them (the decision registry page). */
  decisions?: { decision_id?: string; question: string; choice: string; reason?: string; decided_by?: MemberId; decided_at?: number; reopened_at?: number | null }[];
};

export type Notice = { type: "notice"; ok: boolean; text: string; catchup?: CatchUp; reflection?: Reflection };
export type Answer = Notice | { type: "state"; ok: boolean; state: ProjectState };

export type ServerEvent =
  | { type: "hello"; agentName: string; group: Group; me: Person; members: Person[]; messages: ChatMessage[]; thinking?: boolean }
  | { type: "message"; message: ChatMessage }
  | { type: "members"; members: Person[] }
  /** The space was renamed (Project settings): every open tab shows the new name. */
  | { type: "group"; group: Group }
  | { type: "proposal"; proposal: Proposal }
  | { type: "state"; state: ProjectState }
  | { type: "status"; coordinator: "unavailable" }
  /** Cadence is working on an answer to a member who called it (the adapter clears it when the answer is posted). */
  | { type: "typing"; on: boolean }
  | { type: "reply"; requestId: string; answer: Answer }
  | { type: "error"; text: string }
  | { type: "deleted" };
