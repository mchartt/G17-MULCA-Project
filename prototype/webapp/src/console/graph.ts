// What waits on what, laid out for drawing: a pure function over the saved
// tasks (no clock, no DOM), so the layout is tested without a browser.
// Needed tasks sit on the left, tasks that wait on them to the right.
import type { Task } from "./plan";
import { waitingOn } from "./plan";

export type GraphNode = { id: string; task: Task; layer: number; row: number; waiting: boolean };
/** `to` waits on `from`. */
export type GraphEdge = { from: string; to: string };

export function layoutDependencies(tasks: Task[]): { nodes: GraphNode[]; edges: GraphEdge[]; layers: number; rows: number } {
  const known = new Set(tasks.flatMap((task) => (task.task_id ? [task.task_id] : [])));
  const edges: GraphEdge[] = tasks.flatMap((task) => (task.depends_on ?? []).filter((id) => known.has(id) && task.task_id).map((id) => ({ from: id, to: task.task_id! })));
  const involved = new Set(edges.flatMap((e) => [e.from, e.to]));
  if (involved.size === 0) return { nodes: [], edges: [], layers: 0, rows: 0 };

  const needs = new Map<string, string[]>();
  for (const e of edges) needs.set(e.to, [...(needs.get(e.to) ?? []), e.from]);

  // The layer of a task: one more than the deepest task it needs. The guard only matters for a loop,
  // which the server refuses; a page must still draw something if one ever got in.
  const layers = new Map<string, number>();
  const visiting = new Set<string>();
  const layerOf = (id: string): number => {
    const cached = layers.get(id);
    if (cached !== undefined) return cached;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const layer = Math.max(-1, ...(needs.get(id) ?? []).map(layerOf)) + 1;
    visiting.delete(id);
    layers.set(id, layer);
    return layer;
  };

  const waiting = new Map(waitingOn(tasks).map((row) => [row.task.task_id!, row.waiting]));
  const rowsPerLayer = new Map<number, number>();
  const nodes = tasks
    .filter((task) => task.task_id && involved.has(task.task_id))
    .map((task): GraphNode => {
      const layer = layerOf(task.task_id!);
      const row = rowsPerLayer.get(layer) ?? 0;
      rowsPerLayer.set(layer, row + 1);
      return { id: task.task_id!, task, layer, row, waiting: waiting.get(task.task_id!) ?? false };
    });
  return { nodes, edges, layers: Math.max(...nodes.map((n) => n.layer)) + 1, rows: Math.max(...rowsPerLayer.values()) };
}
