// The plan as lists to show: what comes next, and what is due day by day.
// Pure functions over the saved project state (easy to test, no clock inside).
import type { MemberId, Milestone, ProjectState } from "../lib/types";

export type Task = NonNullable<ProjectState["tasks"]>[number];

/** What a member changes on a task by hand. `owner: null` = nobody, `due: null` = no date. */
export type TaskEdit = { status?: string; owner?: MemberId | null; due?: string | null; title?: string; description?: string; waitsOn?: string[]; progress?: number; remove?: true };
/** `waitsOn` holds task ids; `description` and `waitsOn` are optional (the "New task" popup). */
export type NewTask = { title: string; owner: MemberId | null; due: string | null; description?: string; waitsOn?: string[] };
export type MilestoneEdit = { add: string; due: string | null } | { milestone: string; title?: string; due?: string | null; remove?: true };

export const STATUSES = ["todo", "doing", "done", "blocked"];

/** Earliest date first; no date last; the saved order otherwise. */
function byDate<T extends { due_date?: string | null }>(a: T, b: T): number {
  if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date);
  return a.due_date ? -1 : b.due_date ? 1 : 0;
}

/** The open tasks a member should see first: not done, earliest date first. */
export function upNext(tasks: Task[], limit: number): { shown: Task[]; open: number } {
  const open = tasks.filter((t) => t.status !== "done").sort(byDate);
  return { shown: open.slice(0, limit), open: open.length };
}

/** The milestones still ahead (or without a date), earliest first. */
export function nextMilestones(milestones: Milestone[], today: string, limit: number): Milestone[] {
  return milestones.filter((m) => !m.due_date || m.due_date >= today).sort(byDate).slice(0, limit);
}

export type Day = { key: string; label: string; late: boolean; milestones: Milestone[]; tasks: Task[] };

/**
 * Day by day: one group for everything open that is already late, then one
 * per date in order, then what has no date. Done tasks are left out; passed
 * milestones too.
 */
export function agenda(tasks: Task[], milestones: Milestone[], today: string): Day[] {
  const open = tasks.filter((t) => t.status !== "done");
  const days = new Map<string, Day>();
  const day = (key: string, label: string, late = false) => {
    if (!days.has(key)) days.set(key, { key, label, late, milestones: [], tasks: [] });
    return days.get(key)!;
  };
  for (const t of open.filter((t) => t.due_date && t.due_date < today).sort(byDate)) day("late", "Late", true).tasks.push(t);
  const dates = [...new Set([...open, ...milestones].map((x) => x.due_date).filter((d): d is string => !!d && d >= today))].sort();
  for (const date of dates) {
    const d = day(date, date === today ? "Today" : dayLabel(date));
    d.milestones.push(...milestones.filter((m) => m.due_date === date));
    d.tasks.push(...open.filter((t) => t.due_date === date));
  }
  const undated = open.filter((t) => !t.due_date);
  const openEnded = milestones.filter((m) => !m.due_date);
  if (undated.length || openEnded.length) {
    const d = day("none", "No date yet");
    d.milestones.push(...openEnded);
    d.tasks.push(...undated);
  }
  return [...days.values()];
}

/** "Mon 30 Nov" from "2026-11-30", read as a calendar day (no time zone shift). */
export function dayLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
}

/** Today as YYYY-MM-DD in the member's own time zone. */
export function todayIso(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

/** What needs a member's eyes today: open tasks already late, and open tasks due today. */
export function todayView(tasks: Task[], today: string): { late: Task[]; today: Task[] } {
  const dated = tasks.filter((t) => t.status !== "done" && t.due_date);
  return {
    late: dated.filter((t) => t.due_date! < today).sort(byDate),
    today: dated.filter((t) => t.due_date === today),
  };
}

/** The milestones as the group thinks of them: a date still ahead, a date already passed, no date yet. */
export function milestoneGroups(milestones: Milestone[], today: string): { toComplete: Milestone[]; passed: Milestone[]; toSchedule: Milestone[] } {
  return {
    toComplete: milestones.filter((m) => m.due_date && m.due_date >= today).sort(byDate),
    passed: milestones.filter((m) => m.due_date && m.due_date < today).sort(byDate),
    toSchedule: milestones.filter((m) => !m.due_date),
  };
}

export type Waiting = { task: Task; needs: { task: Task; done: boolean }[]; waiting: boolean };

/**
 * Who waits on whom: one row per task that waits on something. `waiting` is
 * true while the task is open and at least one task it needs is not done.
 * A task that waits on something no longer in the plan simply drops that link.
 */
export function waitingOn(tasks: Task[]): Waiting[] {
  const byId = new Map(tasks.filter((t) => t.task_id).map((t) => [t.task_id!, t]));
  return tasks
    .map((task) => {
      const needs = (task.depends_on ?? []).flatMap((id) => {
        const found = byId.get(id);
        return found ? [{ task: found, done: found.status === "done" }] : [];
      });
      return { task, needs, waiting: task.status !== "done" && needs.some((n) => !n.done) };
    })
    .filter((row) => row.needs.length > 0);
}

/** A few honest numbers about the plan as it stands (the Reflection page). No judgement of people. */
export function planFacts(tasks: Task[], milestones: Milestone[], today: string) {
  const open = tasks.filter((t) => t.status !== "done");
  const groups = milestoneGroups(milestones, today);
  return {
    tasks: tasks.length,
    done: tasks.length - open.length,
    late: open.filter((t) => t.due_date && t.due_date < today).length,
    noOwner: open.filter((t) => !t.owner_id).length,
    noDate: open.filter((t) => !t.due_date).length,
    milestones: milestones.length,
    milestonesPassed: groups.passed.length,
    milestonesToSchedule: groups.toSchedule.length,
  };
}
