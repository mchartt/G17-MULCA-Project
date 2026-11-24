import type { ChatMessage, Proposal } from "../lib/types";
import { dotFor, emptySpace, reduce } from "./space";

const msg = (id: number, text: string, author: ChatMessage["author"] = { id: 1, name: "Ada" }): ChatMessage => ({ id, author, channel: "web", text, ts: 0 });
const proposal = (status: Proposal["status"]): Proposal => ({ proposal_id: "p1", kind: "charter", status, payload: {} });

test("hello sets group, me, members and the history", () => {
  const s = reduce(emptySpace, { type: "hello", agentName: "Cadence", group: { id: 1, name: "T", inviteCode: "ABC" }, me: { id: 1, name: "Ada" }, members: [{ id: 1, name: "Ada" }], messages: [msg(1, "hi")] });
  expect(s.group?.inviteCode).toBe("ABC");
  expect(s.timeline).toHaveLength(1);
});

test("hello puts the answered cards back between the messages, at the time they were posted", () => {
  const at = (id: number, ts: number): ChatMessage => ({ ...msg(id, `m${id}`), ts });
  const card = (id: string, status: Proposal["status"]): Proposal => ({ proposal_id: id, kind: "task_owner", status, payload: {}, names: { "7": "Matteo" } });
  const hello = {
    type: "hello" as const, agentName: "Cadence", group: { id: 1, name: "T", inviteCode: "ABC" }, me: { id: 1, name: "Ada" }, members: [],
    messages: [at(1, 10), at(2, 20), at(3, 30)],
    cards: [{ ts: 20, proposal: card("a", "applied") }, { ts: 25, proposal: card("b", "pending") }, { ts: 99, proposal: card("c", "rejected") }],
  };
  const s = reduce(emptySpace, hello);
  expect(s.timeline.map((t) => (t.kind === "message" ? t.message.id : t.id))).toEqual([1, 2, "a", "b", 3, "c"]);
  expect(s.proposals.a.status).toBe("applied");
  expect(s.names["7"]).toBe("Matteo");
  // The live event that follows for a waiting card changes it in place, no second copy.
  const again = reduce(s, { type: "proposal", proposal: card("b", "pending") });
  expect(again.timeline.filter((t) => t.kind === "proposal" && t.id === "b")).toHaveLength(1);
  // A reconnect sends them again: still one copy each.
  expect(reduce(again, hello).timeline).toHaveLength(6);
});

test("a streamed reply updates the same message instead of adding one", () => {
  let s = reduce(emptySpace, { type: "message", message: msg(7, "Step", null) });
  s = reduce(s, { type: "message", message: msg(7, "Stepping in because…", null) });
  expect(s.timeline).toEqual([{ kind: "message", message: msg(7, "Stepping in because…", null) }]);
});

test("a proposal appears once in the timeline and its later updates change it in place", () => {
  let s = reduce(emptySpace, { type: "proposal", proposal: proposal("pending") });
  s = reduce(s, { type: "proposal", proposal: proposal("applied") });
  expect(s.timeline).toEqual([{ kind: "proposal", id: "p1" }]);
  expect(s.proposals.p1.status).toBe("applied");
});

test("the coordinator is unavailable until it answers again", () => {
  let s = reduce(emptySpace, { type: "status", coordinator: "unavailable" });
  expect(s.coordinator).toBe("unavailable");
  s = reduce(s, { type: "message", message: msg(1, "still me") });
  expect(s.coordinator).toBe("unavailable");
  s = reduce(s, { type: "message", message: msg(2, "Back", null) });
  expect(s.coordinator).toBe("available");
});

test("members, state and unknown events", () => {
  let s = reduce(emptySpace, { type: "members", members: [{ id: 5, name: "Eve" }] });
  s = reduce(s, { type: "state", state: { charter: { goal: "G" } } });
  expect(s.members[0].name).toBe("Eve");
  expect(s.state?.charter?.goal).toBe("G");
  expect(reduce(s, { type: "error", text: "x" })).toBe(s);
});

test("each member keeps the same dot colour", () => {
  const members = [{ id: 10, name: "A" }, { id: 20, name: "B" }];
  expect(dotFor(10, members)).toBe("var(--m1)");
  expect(dotFor(20, members)).toBe("var(--m2)");
});
