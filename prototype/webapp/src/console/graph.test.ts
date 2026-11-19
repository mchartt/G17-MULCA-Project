import { layoutDependencies } from "./graph";
import type { Task } from "./plan";

const t = (task_id: string, status = "todo", depends_on: string[] = []): Task => ({ task_id, title: task_id.toUpperCase(), status, owner_id: 1, due_date: null, depends_on });

test("no dependency, no graph", () => {
  expect(layoutDependencies([t("a"), t("b")])).toEqual({ nodes: [], edges: [], layers: 0, rows: 0 });
});

test("a chain goes left to right: what is needed first, what waits after", () => {
  const g = layoutDependencies([t("c", "todo", ["b"]), t("b", "todo", ["a"]), t("a", "doing")]);
  expect(g.nodes.map((n) => [n.id, n.layer]).sort()).toEqual([["a", 0], ["b", 1], ["c", 2]]);
  expect(g.edges).toEqual(expect.arrayContaining([{ from: "a", to: "b" }, { from: "b", to: "c" }]));
  expect(g.layers).toBe(3);
});

test("tasks of the same layer take rows in the order of the plan; a task that needs two sits after the later of them", () => {
  const g = layoutDependencies([t("a"), t("b"), t("x", "todo", ["a", "b"]), t("y", "todo", ["x"]), t("z", "todo", ["a"])]);
  const at = (id: string) => g.nodes.find((n) => n.id === id)!;
  expect([at("a").row, at("b").row]).toEqual([0, 1]);
  expect(at("x").layer).toBe(1);
  expect(at("z").layer).toBe(1);
  expect(at("y").layer).toBe(2);
  expect([at("x").row, at("z").row]).toEqual([0, 1]);
  expect(g.rows).toBe(2);
});

test("tasks outside every dependency are left out, and a link to a task that is gone is dropped", () => {
  const g = layoutDependencies([t("a"), t("b", "todo", ["a", "gone"]), t("lonely")]);
  expect(g.nodes.map((n) => n.id).sort()).toEqual(["a", "b"]);
  expect(g.edges).toEqual([{ from: "a", to: "b" }]);
});

test("a node is waiting while it is open and something it needs is not done", () => {
  const g = layoutDependencies([t("a", "doing"), t("b", "todo", ["a"]), t("c", "done"), t("d", "todo", ["c"]), t("e", "done", ["a"])]);
  const waiting = Object.fromEntries(g.nodes.map((n) => [n.id, n.waiting]));
  expect(waiting).toEqual({ a: false, b: true, c: false, d: false, e: false });
});

test("a loop that should never exist does not hang the page", () => {
  const g = layoutDependencies([t("a", "todo", ["b"]), t("b", "todo", ["a"])]);
  expect(g.nodes).toHaveLength(2);
});
