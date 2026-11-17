import { agenda, dayLabel, nextMilestones, upNext, type Task } from "./plan";

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
