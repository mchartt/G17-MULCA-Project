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
export type CommandName = "profile" | "kickoff" | "state" | "planning" | "checkin" | "task" | "why";

/** Why a proactive card exists (M3): strategy, topic, and the messages behind it. */
export type ProactiveContext = {
  strategy_id: string;
  topic: string;
  evidence: { speaker: string; text: string; at_ms: number }[];
};

export type Milestone = { title: string; due_date?: string | null; status?: string };

export type Proposal = {
  proposal_id: string;
  kind: string;
  status: ProposalStatus;
  rationale?: string;
  expires_at?: number | null;
  payload: {
    goal?: string;
    deliverables?: string[];
    milestones?: Milestone[];
    // M3 proactive cards (task_owner, delegation, decision)
    context?: ProactiveContext;
    title?: string;
    owner_id?: number | null;
    due_date?: string | null;
    return_to?: string;
    question?: string;
    options?: { label: string; argument?: string }[];
    // M4 cards (plan, checkin, blocker)
    items?: { title: string; owner_id?: number | null; reason?: string; due_date?: string | null }[];
    findings?: string[];
    helper_id?: number | null;
    [key: string]: unknown;
  };
};

export type ProjectState = {
  charter?: { goal: string; deliverables?: string[]; confirmed_by?: number } | null;
  milestones?: Milestone[];
  members?: { member_id?: number; display_name: string; discipline?: string; skills?: string; weekly_hours?: number }[];
  tasks?: { task_id?: string; title: string; status: string; owner_id?: number | null; due_date?: string | null }[];
  decisions?: { question: string; choice: string; reason?: string }[];
};

export type Notice = { type: "notice"; ok: boolean; text: string };
export type Answer = Notice | { type: "state"; ok: boolean; state: ProjectState };

export type ServerEvent =
  | { type: "hello"; agentName: string; group: Group; me: Person; members: Person[]; messages: ChatMessage[] }
  | { type: "message"; message: ChatMessage }
  | { type: "members"; members: Person[] }
  | { type: "proposal"; proposal: Proposal }
  | { type: "state"; state: ProjectState }
  | { type: "status"; coordinator: "unavailable" }
  | { type: "reply"; requestId: string; answer: Answer }
  | { type: "error"; text: string }
  | { type: "deleted" };
