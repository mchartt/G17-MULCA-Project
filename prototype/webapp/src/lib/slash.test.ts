import { expect, test } from "vitest";
import { mentionParts, parseSlash, suggest } from "./slash";

test("an ordinary message is not a command", () => {
  expect(parseSlash("hello / world")).toBeNull();
});

test("a command keeps its text; /coordinator in front works as on Discord", () => {
  expect(parseSlash("/kickoff Deliver the report by 2 December")).toEqual({ kind: "run", name: "kickoff", rest: "Deliver the report by 2 December" });
  expect(parseSlash("/coordinator planning API; UI")).toEqual({ kind: "run", name: "planning", rest: "API; UI" });
  expect(parseSlash("/CHECKIN")).toEqual({ kind: "run", name: "checkin", rest: "" });
});

test("/task needs a number and a known status", () => {
  expect(parseSlash("/task 2 Done")).toEqual({ kind: "task", task: "2", status: "done" });
  expect(parseSlash("/task two done")).toMatchObject({ kind: "say" });
});

test("an unknown command and /help answer with the list", () => {
  expect(parseSlash("/dance")).toMatchObject({ kind: "say", text: expect.stringContaining("/kickoff") });
  expect(parseSlash("/help")).toMatchObject({ kind: "say", text: expect.stringContaining("/checkin") });
  expect(parseSlash("/why")).toMatchObject({ kind: "say" });
});

test("suggestions: commands after '/', the tag after '@'", () => {
  expect(suggest("/ch").map((s) => s.fill)).toEqual(["/checkin "]);
  expect(suggest("/").length).toBeGreaterThan(5);
  expect(suggest("hi @co")).toEqual([{ label: "@coordinator", about: "Ask Cadence directly", fill: "hi @coordinator " }]);
  expect(suggest("hi @coordinator")).toEqual([]);
  expect(suggest("mail me@x")).toEqual([]);
  expect(suggest("/kickoff text")).toEqual([]);
});

test("/planning keeps tasks written one per line; /ask needs a question", () => {
  expect(parseSlash("/planning Server\nUI")).toEqual({ kind: "run", name: "planning", rest: "Server\nUI" });
  expect(parseSlash("/ask when is the demo?")).toEqual({ kind: "run", name: "ask", rest: "when is the demo?" });
  expect(parseSlash("/ask")).toMatchObject({ kind: "say" });
});

test("after '@' the teammates are offered too, with their exact names", () => {
  const people = ["Matteo Cesandri", "Matias", "Gabriele"];
  expect(suggest("@", people).map((s) => s.label)).toEqual(["@coordinator", "@Matteo Cesandri", "@Matias", "@Gabriele"]);
  expect(suggest("ask @mat", people).map((s) => s.fill)).toEqual(["ask @Matteo Cesandri ", "ask @Matias "]);
  expect(suggest("@c", people).map((s) => s.label)).toEqual(["@coordinator"]);
  expect(suggest("@zed", people)).toEqual([]);
});

test("a message is split so every mention can be shown as a tag", () => {
  const people = ["Ada", "Ada Lovelace"];
  expect(mentionParts("hi @Ada Lovelace and @ada, ask @Coordinator", people)).toEqual([
    { text: "hi ", mention: false },
    { text: "@Ada Lovelace", mention: true },
    { text: " and ", mention: false },
    { text: "@ada", mention: true },
    { text: ", ask ", mention: false },
    { text: "@Coordinator", mention: true },
  ]);
  expect(mentionParts("@Adam is not @Ada.", people).filter((p) => p.mention).map((p) => p.text)).toEqual(["@Ada"]);
  expect(mentionParts("a (regex) name @A.B+", ["A.B+"]).at(-1)).toEqual({ text: "@A.B+", mention: true });
});

test("/language takes en, it or auto", () => {
  expect(parseSlash("/language it")).toEqual({ kind: "run", name: "language", rest: "it" });
  expect(parseSlash("/language")?.kind).toBe("say");
  expect(parseSlash("/language french")?.kind).toBe("say");
});

test("/task add makes a new task from the rest of the line", () => {
  expect(parseSlash("/task add Write the report")).toEqual({ kind: "addtask", title: "Write the report" });
  expect(parseSlash("/task add")?.kind).toBe("say");
  expect(parseSlash("/task 2 done")).toEqual({ kind: "task", task: "2", status: "done" });
});
