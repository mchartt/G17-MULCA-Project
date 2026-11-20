import { render, screen, within } from "@testing-library/react";
import { PlanStatus, ProgressRing, WeekByDay } from "./ReflectionCharts";

// 20/11: the Reflection's charts carry their numbers as text, never colour alone; group counts only.
test("day by day: two small charts on one day axis, and a table with every number", () => {
  const days = ["2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-21", "2026-11-22"].map((day, i) => ({ day, messages: i * 2, done: i === 4 ? 3 : 0 }));
  render(<WeekByDay days={days} today="2026-11-20" />);
  expect(screen.getByText("Messages", { selector: "figcaption span" }).closest("figure")).toHaveTextContent("42");
  expect(screen.getByText("Tasks done", { selector: "figcaption span" }).closest("figure")).toHaveTextContent("3");
  const table = screen.getByRole("table", { name: "The week day by day" });
  expect(within(table).getAllByRole("row")).toHaveLength(8);
});

test("the plan by status: a bar named in words and a legend with each count", () => {
  const tasks = [
    { task_id: "a", title: "A", status: "done" },
    { task_id: "b", title: "B", status: "doing" },
    { task_id: "c", title: "C", status: "todo", depends_on: ["b"] },
    { task_id: "d", title: "D", status: "todo" },
  ];
  render(<PlanStatus tasks={tasks} />);
  expect(screen.getByRole("img", { name: "1 done, 1 in progress, 1 waiting, 1 to do" })).toBeInTheDocument();
});

test("the progress ring says the share in words", () => {
  render(<ProgressRing done={3} total={4} />);
  expect(screen.getByRole("img", { name: "75% of the plan done: 3 of 4 tasks" })).toBeInTheDocument();
});
