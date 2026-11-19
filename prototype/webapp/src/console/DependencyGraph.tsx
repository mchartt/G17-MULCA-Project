import { layoutDependencies } from "./graph";
import type { Task } from "./plan";

const NODE_W = 176;
const NODE_H = 46;
const GAP_X = 68;
const GAP_Y = 16;
const PAD = 12;
const MAX_CHARS = 24;

const short = (title: string) => (title.length > MAX_CHARS ? `${title.slice(0, MAX_CHARS - 1)}…` : title);

/**
 * What waits on what, drawn: needed tasks on the left, the ones that wait on
 * them to the right, an arrow for each "waits on". Plain SVG, no library.
 * The list under it says the same in words (it is the text alternative).
 * Solid border = the group decided it (saved in the plan).
 */
export function DependencyGraph({ tasks }: { tasks: Task[] }) {
  const graph = layoutDependencies(tasks);
  if (graph.nodes.length === 0) return null;
  const width = PAD * 2 + graph.layers * NODE_W + (graph.layers - 1) * GAP_X;
  const height = PAD * 2 + graph.rows * NODE_H + (graph.rows - 1) * GAP_Y;
  const at = (layer: number, row: number) => ({ x: PAD + layer * (NODE_W + GAP_X), y: PAD + row * (NODE_H + GAP_Y) });
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const waitingCount = graph.nodes.filter((n) => n.waiting).length;

  return (
    <div className="depgraph">
      <svg role="img" aria-label={`Dependency graph: ${graph.nodes.length} tasks, ${graph.edges.length} links, ${waitingCount} waiting. The same facts are listed below.`} width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <marker id="depgraph-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0 L8 4 L0 8 z" className="depgraph__arrow" />
          </marker>
        </defs>
        {graph.edges.map((edge) => {
          const from = byId.get(edge.from)!;
          const to = byId.get(edge.to)!;
          const a = at(from.layer, from.row);
          const b = at(to.layer, to.row);
          const x1 = a.x + NODE_W;
          const y1 = a.y + NODE_H / 2;
          const x2 = b.x;
          const y2 = b.y + NODE_H / 2;
          const mid = (x1 + x2) / 2;
          return <path key={`${edge.from}-${edge.to}`} d={`M${x1} ${y1} C${mid} ${y1}, ${mid} ${y2}, ${x2 - 2} ${y2}`} className="depgraph__edge" markerEnd="url(#depgraph-arrow)" />;
        })}
        {graph.nodes.map((node) => {
          const { x, y } = at(node.layer, node.row);
          const state = node.task.status === "done" ? "done" : node.waiting ? "waiting" : "ready";
          return (
            <g key={node.id} className={`depgraph__node depgraph__node--${state}`} transform={`translate(${x} ${y})`}>
              <title>{`${node.task.title}: ${state === "done" ? "done" : state === "waiting" ? "waiting" : "ready to start"}`}</title>
              <rect width={NODE_W} height={NODE_H} rx={10} />
              <text x={12} y={19} className="depgraph__title">{short(node.task.title)}</text>
              <text x={12} y={35} className="depgraph__state">{state === "done" ? "Done" : state === "waiting" ? "Waiting" : "Ready to start"}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
