// Sample data for the preview screens (src/preview/). Nothing here comes from
// MUCA-Server or is saved: the screens show where Cadence is going, with the
// group's own design decisions (one plan, one memory, a member's click applies).

import type { Person, Proposal } from "../lib/types";

export const MEMBERS: Person[] = [
  { id: 1, name: "Ada" },
  { id: 2, name: "Bruno" },
  { id: 3, name: "Chiara" },
  { id: 4, name: "Dario" },
];
export const ME = MEMBERS[0];

// ---------- Plan around calendars ----------

export const DAYS = ["Mon 23", "Tue 24", "Wed 25", "Thu 26", "Fri 27"];
export const DAY_START = 9;
export const DAY_END = 19;

/** [day index, from hour, to hour]: all a connected calendar tells Cadence. */
export type Busy = [day: number, from: number, to: number];

export const BUSY: Record<number, Busy[]> = {
  1: [[0, 9, 13], [1, 9, 11], [1, 14, 16], [2, 9, 13], [3, 11, 13], [3, 14, 18], [4, 9, 12]],
  2: [[0, 9, 18], [1, 9, 17], [2, 9, 14], [2, 16, 19], [3, 9, 10], [3, 13, 19], [4, 9, 17]],
  3: [[0, 11, 13], [1, 9, 12], [2, 10, 12], [2, 15, 17], [3, 11, 15], [4, 14, 16]],
  4: [[0, 14, 18], [1, 10, 13], [1, 15, 17], [2, 9, 11], [2, 15, 19], [3, 12, 13], [3, 16, 19], [4, 9, 11]],
};

export type Slot = { day: number; from: number; to: number };

/** The windows in which nobody is busy, day by day. */
export function freeForAll(busy: Record<number, Busy[]>, days = DAYS.length): Slot[] {
  const slots: Slot[] = [];
  for (let day = 0; day < days; day++) {
    let open: number | null = null;
    for (let hour = DAY_START; hour <= DAY_END; hour++) {
      const taken =
        hour === DAY_END || Object.values(busy).some((blocks) => blocks.some(([d, from, to]) => d === day && hour >= from && hour < to));
      if (!taken && open === null) open = hour;
      if (taken && open !== null) {
        slots.push({ day, from: open, to: hour });
        open = null;
      }
    }
  }
  return slots;
}

/** Hours a member has free between 9 and 19 over the week. */
export function freeHours(blocks: Busy[]): number {
  return DAYS.length * (DAY_END - DAY_START) - blocks.reduce((sum, [, from, to]) => sum + to - from, 0);
}

export const hourLabel = (hour: number) => `${hour}:00`;
export const slotLabel = (slot: Slot) => `${DAYS[slot.day].split(" ")[0]} ${hourLabel(slot.from)}`;

/** The draft is due on Thursday: only the slots before it are offered (three at most, like every card). */
export const MEETING_SLOTS = freeForAll(BUSY).filter((s) => s.day < 3).slice(0, 3);

export const MEETING_CARD: Proposal = {
  proposal_id: "preview-find-a-time",
  kind: "decision",
  status: "pending",
  rationale: "Stepping in because the report draft is due on Thursday and no meeting is set: these hours are free for all four of you.",
  payload: {
    question: "When do you meet to merge the report?",
    options: MEETING_SLOTS.map((s) => ({ label: slotLabel(s), argument: `everyone free until ${hourLabel(s.to)}` })),
    context: {
      strategy_id: "cs14_find_a_time",
      topic: "Meeting before the report draft",
      evidence: [
        { speaker: "Chiara · Discord", text: "We need an hour together to merge the report before Thursday.", at_ms: 0 },
        { speaker: "Dario · Discord", text: "When though? I never know who is free.", at_ms: 0 },
      ],
    },
  },
};

// ---------- Catch up ----------

export type Line = { author: Person | null; text: string; channel: string };

export const THURSDAY: Line[] = [
  { author: MEMBERS[1], channel: "discord", text: "Think-aloud or a questionnaire for the evaluation? We keep going back and forth." },
  { author: MEMBERS[2], channel: "discord", text: "Think-aloud gives us quotes for the report. Five users are enough." },
  { author: MEMBERS[3], channel: "discord", text: "Fine by me. Someone should book the usability lab for Tuesday then." },
];

export const THURSDAY_DECISION: Proposal = {
  proposal_id: "preview-decision",
  kind: "decision",
  status: "applied",
  rationale: "Stepping in because the same question has two options and no decision.",
  payload: {
    question: "Which evaluation method?",
    options: [
      { label: "Think-aloud with 5 users", argument: "quotes for the report" },
      { label: "Questionnaire", argument: "faster to analyse" },
    ],
  },
};

export const MISSED = [
  {
    title: "Decision: the evaluation is a think-aloud with 5 users.",
    source: "Discord call, Thu 19 Nov, 18:12 · chosen by Chiara",
  },
  {
    title: "A task waits for you: book the usability lab by Tue 24 Nov.",
    source: "Discord #group-17, Thu 19 Nov, 18:31 · said by Dario",
  },
];

export const LAB_CARD: Proposal = {
  proposal_id: "preview-lab",
  kind: "task_owner",
  status: "pending",
  rationale: "Stepping in because this action has no owner yet. Ada has the lab access, so I suggest her; anyone can take it.",
  payload: { title: "Book the usability lab", due_date: "2026-11-24", owner_id: 1 },
};

// ---------- Connections ----------

export type Connection = {
  id: string;
  name: string;
  detail: string;
  reads: string;
  connected: boolean;
  /** The web space is the home of the project: it cannot be disconnected. */
  fixed?: boolean;
};

export const CHANNELS: Connection[] = [
  { id: "web", name: "Cadence web space", detail: "Plan, decisions, reflection and a group chat", reads: "Everything written in the space", connected: true, fixed: true },
  { id: "discord", name: "Discord", detail: "#group-17 and its voice channel · linked by Ada with /coordinator join", reads: "Messages of the linked channel and calls it is invited to; answers in text, never in voice", connected: true },
  { id: "slack", name: "Slack", detail: "One channel of your workspace", reads: "Messages of the linked channel only", connected: false },
];

export const SOURCES: Connection[] = [
  { id: "calendar", name: "Google Calendar", detail: "3 of 4 members connected their own", reads: "Busy and free times only, never what an event is", connected: true },
  { id: "drive", name: "Google Drive", detail: "The project folder", reads: "File names and who edited last, not the content", connected: false },
  { id: "github", name: "GitHub", detail: "The project repository", reads: "Open issues and pull requests, not the code", connected: false },
];

// ---------- Reflection ----------

export const TILES = [
  { label: "Delivered", value: "2 Dec", note: "on the deadline" },
  { label: "Tasks done", value: "16 of 18", note: "2 dropped by a group decision" },
  { label: "Decisions", value: "7", note: "1 reopened" },
  { label: "Cards from Cadence", value: "23", note: "15 confirmed · 5 not now · 3 expired" },
];

export const MILESTONES = [
  { title: "Project charter confirmed", planned: "9 Nov", actual: "9 Nov", late: 0 },
  { title: "Evaluation protocol", planned: "16 Nov", actual: "19 Nov", late: 3 },
  { title: "Report draft", planned: "26 Nov", actual: "27 Nov", late: 1 },
  { title: "Prototype freeze", planned: "30 Nov", actual: "30 Nov", late: 0 },
  { title: "Demo Madness", planned: "2 Dec", actual: "2 Dec", late: 0 },
];

export const SLOWER = [
  { title: "Recruiting five users", planned: 2, took: 5, who: "Bruno, check-in of 17 Nov", note: "Finding people outside the course took longer than I expected." },
  { title: "Merging the report", planned: 1, took: 3, who: "Chiara, check-in of 26 Nov", note: "Three writing styles in one document: we should have agreed a template first." },
];

/** Share of the group's messages by place, in percent. */
export const PLACES = [
  { name: "Discord text", share: 46 },
  { name: "Web space", share: 31 },
  { name: "Discord calls", share: 23 },
];

export const RETRO = [
  { column: "Start", items: ["Agree a report template before anyone writes", "Book shared rooms and labs the day a date is set"] },
  { column: "Stop", items: ["Reopening a closed decision without new information (once, two days lost)"] },
  { column: "Continue", items: ["The Monday check-in: it found late work early four times out of five", "One owner per task: no task stayed without one for more than a day"] },
];
