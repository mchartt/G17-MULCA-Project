// Everything the console shows, rebuilt from the adapter's events by one pure
// function (easy to test, easy to explain: event in, new state out).
import type { ChatMessage, Group, Person, ProjectState, Proposal, ServerEvent } from "../lib/types";

export type TimelineItem = { kind: "message"; message: ChatMessage } | { kind: "proposal"; id: string };

export type Space = {
  agentName: string;
  group: Group | null;
  me: Person | null;
  members: Person[];
  timeline: TimelineItem[];
  proposals: Record<string, Proposal>;
  state: ProjectState | null;
  coordinator: "available" | "unavailable";
};

export const emptySpace: Space = {
  agentName: "Cadence",
  group: null,
  me: null,
  members: [],
  timeline: [],
  proposals: {},
  state: null,
  coordinator: "available",
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
      return { ...space, timeline, coordinator: event.message.author ? space.coordinator : "available" };
    }
    case "members":
      return { ...space, members: event.members };
    case "proposal": {
      const id = event.proposal.proposal_id;
      const known = id in space.proposals;
      return {
        ...space,
        proposals: { ...space.proposals, [id]: event.proposal },
        timeline: known ? space.timeline : [...space.timeline, { kind: "proposal", id }],
      };
    }
    case "state":
      return { ...space, state: event.state, coordinator: "available" };
    case "status":
      return { ...space, coordinator: event.coordinator };
    default:
      return space;
  }
}

/** The member's colour dot, stable for a given id (the stickers on the board). */
export const DOT_COLOURS = ["var(--dot-sage)", "var(--dot-slate)", "var(--dot-ochre)", "var(--dot-coral)"];
export function dotFor(id: number, members: Person[]): string {
  const index = members.findIndex((m) => m.id === id);
  return DOT_COLOURS[(index >= 0 ? index : id) % DOT_COLOURS.length];
}
