// Everything the console shows, rebuilt from the adapter's events by one pure
// function (easy to test, easy to explain: event in, new state out).
import type { ChatMessage, Group, MemberId, Names, Person, ProjectState, Proposal, ServerEvent } from "../lib/types";

export type TimelineItem = { kind: "message"; message: ChatMessage } | { kind: "proposal"; id: string };

export type Space = {
  agentName: string;
  group: Group | null;
  me: Person | null;
  members: Person[];
  timeline: TimelineItem[];
  proposals: Record<string, Proposal>;
  state: ProjectState | null;
  // id -> name for members of linked channels too (Discord, Slack).
  names: Names;
  coordinator: "available" | "unavailable";
  /** Cadence is preparing an answer: the chat shows "Cadence is thinking…". */
  thinking: boolean;
};

export const emptySpace: Space = {
  agentName: "Cadence",
  group: null,
  me: null,
  members: [],
  timeline: [],
  proposals: {},
  state: null,
  names: {},
  coordinator: "available",
  thinking: false,
};

export function reduce(space: Space, event: ServerEvent): Space {
  switch (event.type) {
    case "hello":
      return {
        ...space,
        agentName: event.agentName,
        group: event.group,
        me: event.me,
        members: event.members,
        // A reconnect: a "thinking" line from before the drop must not stay forever.
        thinking: false,
        // History replaces the timeline; cards already seen this session stay where they were.
        timeline: [
          ...event.messages.map((m) => ({ kind: "message" as const, message: m })),
          ...space.timeline.filter((t) => t.kind === "proposal"),
        ],
      };
    case "message": {
      // A streamed reply arrives several times with the same id and a longer text.
      const at = space.timeline.findIndex((t) => t.kind === "message" && t.message.id === event.message.id);
      const item: TimelineItem = { kind: "message", message: event.message };
      const timeline = at >= 0 ? space.timeline.map((t, i) => (i === at ? item : t)) : [...space.timeline, item];
      // Cadence's own message ends its "thinking" line, whatever the adapter sends after.
      return event.message.author
        ? { ...space, timeline }
        : { ...space, timeline, coordinator: "available", thinking: false };
    }
    case "group":
      return { ...space, group: event.group };
    case "members":
      return { ...space, members: event.members };
    case "proposal": {
      const id = event.proposal.proposal_id;
      const known = id in space.proposals;
      return {
        ...space,
        proposals: { ...space.proposals, [id]: event.proposal },
        names: { ...space.names, ...event.proposal.names },
        timeline: known ? space.timeline : [...space.timeline, { kind: "proposal", id }],
      };
    }
    case "state":
      return { ...space, state: event.state, names: { ...space.names, ...event.state.names }, coordinator: "available" };
    case "status":
      return { ...space, coordinator: event.coordinator, thinking: false };
    case "typing":
      return { ...space, thinking: event.on };
    default:
      return space;
  }
}

/** A member's name: from this space, or from a linked channel (Discord, Slack). */
export function nameOf(id: MemberId | null | undefined, space: Pick<Space, "members" | "names">): string | undefined {
  if (id === null || id === undefined) return undefined;
  return space.members.find((m) => m.id === id)?.name ?? space.names[String(id)];
}

/** The member's colour dot, stable for a given id (the stickers on the board). */
export const DOT_COLOURS = ["var(--m1)", "var(--m2)", "var(--m3)", "var(--m4)", "var(--m5)"];
/** One member's profile, as Cadence keeps it (sent with the project state). */
export type MemberProfile = NonNullable<ProjectState["members"]>[number];

export function profileOf(id: MemberId, state: ProjectState | null): MemberProfile | undefined {
  return state?.members?.find((p) => String(p.member_id) === String(id));
}

/** The short facts of a profile: discipline, skills, hours (shared by the Team panel and the member popup). */
export function profileFacts(p: MemberProfile | undefined): string[] {
  return [p?.discipline?.trim(), p?.skills?.length ? p.skills.join(", ") : "", typeof p?.weekly_hours === "number" ? `${p.weekly_hours} h/week` : ""].filter(
    (f): f is string => !!f,
  );
}

export function dotFor(id: MemberId, members: Person[]): string {
  const index = members.findIndex((m) => m.id === id);
  // Not a web member (a linked channel): a stable colour from the id's last digits.
  const fallback = Number(String(id).slice(-4)) || 0;
  return DOT_COLOURS[(index >= 0 ? index : fallback) % DOT_COLOURS.length];
}
