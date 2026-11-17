import { expect, test } from "vitest";
import { parseSlash, suggest } from "./slash";

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
