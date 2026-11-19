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
export type CommandName = "profile" | "kickoff" | "state" | "planning" | "checkin" | "task" | "why" | "ask" | "catchup" | "language" | "charter" | "milestone";

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
  elsewhere: { channel: string; total: number; messages: { speaker: string; text: string; at: number }[] }[];
};

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
    helper_id?: MemberId | null;
    // CS7 v2 (blocker) and K3 (revisit)
    certainty?: "blocked" | "possible";
    depends_on_title?: string;
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
  tasks?: { task_id?: string; title: string; status: string; owner_id?: MemberId | null; due_date?: string | null; description?: string; depends_on?: string[] }[];
  decisions?: { question: string; choice: string; reason?: string }[];
};

export type Notice = { type: "notice"; ok: boolean; text: string; catchup?: CatchUp };
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
