import { agenda, dayLabel, milestoneGroups, nextMilestones, planFacts, todayView, upNext, waitingOn, type Task } from "./plan";

const task = (title: string, due_date: string | null, status = "todo", owner_id: number | null = 1): Task => ({ task_id: title, title, due_date, status, owner_id });

test("up next: open tasks only, earliest date first, undated last, cut to the limit", () => {
  const tasks = [task("Slides", null), task("Report", "2026-12-01"), task("Old", "2026-11-01", "done"), task("API", "2026-11-20"), task("Test", "2026-11-25")];
  const next = upNext(tasks, 3);
  expect(next.shown.map((t) => t.title)).toEqual(["API", "Test", "Report"]);
  expect(next.open).toBe(4);
});

test("milestones ahead: passed ones are left out, undated ones stay", () => {
  const all = [{ title: "Kickoff", due_date: "2026-11-10" }, { title: "Demo", due_date: "2026-12-02" }, { title: "Tutoring", due_date: null }, { title: "Draft", due_date: "2026-11-23" }];
  expect(nextMilestones(all, "2026-11-17", 5).map((m) => m.title)).toEqual(["Draft", "Demo", "Tutoring"]);
});

test("day by day: late first, then each date with its milestone and tasks, then what has no date", () => {
  const days = agenda(
    [task("API", "2026-11-10"), task("Report", "2026-12-02"), task("Slides", null), task("Shipped", "2026-11-18", "done"), task("Test", "2026-11-17")],
    [{ title: "Demo Madness", due_date: "2026-12-02" }, { title: "Passed", due_date: "2026-11-01" }],
    "2026-11-17",
  );
  expect(days.map((d) => [d.label, d.milestones.map((m) => m.title), d.tasks.map((t) => t.title)])).toEqual([
    ["Late", [], ["API"]],
    ["Today", [], ["Test"]],
    ["Wed 2 Dec", ["Demo Madness"], ["Report"]],
    ["No date yet", [], ["Slides"]],
  ]);
  expect(days[0]!.late).toBe(true);
  expect(agenda([], [], "2026-11-17")).toEqual([]);
});

test("a date is read as a calendar day, whatever the time zone", () => {
  expect(dayLabel("2026-11-30")).toBe("Mon 30 Nov");
  expect(dayLabel("not a date")).toBe("not a date");
});

test("today: open tasks already late (earliest first) and open tasks due today; done, undated and future ones are left out", () => {
  const view = todayView(
    [task("Old", "2026-11-10"), task("Older", "2026-11-05"), task("Now", "2026-11-19"), task("Later", "2026-11-20"), task("Free", null), task("Shipped", "2026-11-12", "done")],
    "2026-11-19",
  );
  expect(view.late.map((t) => t.title)).toEqual(["Older", "Old"]);
  expect(view.today.map((t) => t.title)).toEqual(["Now"]);
  expect(todayView([], "2026-11-19")).toEqual({ late: [], today: [] });
});

test("milestones: a date still ahead, a date already passed, and no date yet", () => {
  const groups = milestoneGroups(
    [{ title: "Demo", due_date: "2026-12-02" }, { title: "Kickoff", due_date: "2026-11-10" }, { title: "Tutoring", due_date: null }, { title: "Draft", due_date: "2026-11-19" }, { title: "Slides" }],
    "2026-11-19",
  );
  expect(groups.toComplete.map((m) => m.title)).toEqual(["Draft", "Demo"]); // today still counts as ahead
  expect(groups.passed.map((m) => m.title)).toEqual(["Kickoff"]);
  expect(groups.toSchedule.map((m) => m.title)).toEqual(["Tutoring", "Slides"]);
});

test("who waits on whom: only tasks that wait on something; waiting while a task they need is not done", () => {
  const api = { ...task("API", "2026-11-20", "doing"), task_id: "api" };
  const shipped = { ...task("Design", null, "done"), task_id: "design" };
  const check = { ...task("Test", "2026-11-25"), task_id: "test", depends_on: ["api", "design", "gone"] };
  const demo = { ...task("Demo", null), task_id: "demo", depends_on: ["design"] };
  const closed = { ...task("Closed", null, "done"), task_id: "closed", depends_on: ["api"] };
  const rows = waitingOn([api, shipped, check, demo, closed]);
  expect(rows.map((r) => [r.task.title, r.needs.map((n) => [n.task.title, n.done]), r.waiting])).toEqual([
    ["Test", [["API", false], ["Design", true]], true], // "gone" is no longer in the plan: its link is dropped
    ["Demo", [["Design", true]], false], // everything it needs is done: ready
    ["Closed", [["API", false]], false], // a done task is not waiting
  ]);
  expect(waitingOn([api])).toEqual([]);
});

test("plan facts: counts only, from open tasks and milestones", () => {
  const facts = planFacts(
    [task("A", "2026-11-10"), task("B", null, "todo", null), task("C", "2026-11-30", "done"), task("D", "2026-12-01", "doing", null)],
    [{ title: "Demo", due_date: "2026-12-02" }, { title: "Kickoff", due_date: "2026-11-10" }, { title: "Tutoring", due_date: null }],
    "2026-11-19",
  );
  expect(facts).toEqual({ tasks: 4, done: 1, late: 1, noOwner: 2, noDate: 1, milestones: 3, milestonesPassed: 1, milestonesToSchedule: 1 });
});
