/**
 * Slash commands typed in the web chat, the same words as on Discord and Slack:
 *   /kickoff <assignment>   /planning <task>; <task>   /checkin   /catchup
 *   /task 2 done            /why <question>   /ask <question>   /plan   /help
 * "/coordinator kickoff ..." works too, so a habit from Discord carries over.
 *
 * A command is one row of COMMANDS (a command table): to add one, add a row
 * here and one case in Console.runSlash. A slash line is never sent to the
 * group as a message.
 */

export type SlashName = "kickoff" | "planning" | "checkin" | "catchup" | "task" | "why" | "ask" | "plan" | "profile" | "help";

export type SlashCommand = { name: SlashName; hint: string; about: string };

export const COMMANDS: SlashCommand[] = [
  { name: "kickoff", hint: "/kickoff <assignment text>", about: "Propose the project charter" },
  { name: "planning", hint: "/planning <task>; <task>; …", about: "Suggest who takes each task" },
  { name: "checkin", hint: "/checkin", about: "Compare the plan with reality" },
  { name: "catchup", hint: "/catchup", about: "What you missed in the other channels" },
  { name: "task", hint: "/task <number> <todo|doing|done|blocked>", about: "Update a task" },
  { name: "why", hint: "/why <question>", about: "Answer from the decision log" },
  { name: "ask", hint: "/ask <question>", about: "Answer from the plan, the dates and the decisions" },
  { name: "plan", hint: "/plan", about: "Show the project plan" },
  { name: "profile", hint: "/profile", about: "Edit your profile" },
  { name: "help", hint: "/help", about: "List these commands" },
];

export const MENTION = "@coordinator";
const STATUSES = ["todo", "doing", "done", "blocked"];

/** What a slash line asks for: a command with its text, or words to show the member. */
export type Slash =
  | { kind: "run"; name: SlashName; rest: string }
  | { kind: "task"; task: string; status: string }
  | { kind: "say"; text: string };

export const HELP = COMMANDS.map((c) => `${c.hint}: ${c.about}`).join("\n");

/** null when the text is an ordinary message. */
export function parseSlash(text: string): Slash | null {
  const line = text.trim();
  if (!line.startsWith("/")) return null;
  let [name = "", ...words] = line.slice(1).split(/\s+/);
  if (name.toLowerCase() === "coordinator") [name = "", ...words] = words;
  const rest = line.slice(line.toLowerCase().indexOf(name.toLowerCase()) + name.length).trim();
  const command = COMMANDS.find((c) => c.name === name.toLowerCase());
  if (!command) return { kind: "say", text: `Unknown command "/${name}".\n${HELP}` };
  if (command.name === "help") return { kind: "say", text: HELP };
  if (command.name === "why" && !rest) return { kind: "say", text: "Ask a question: /why did we choose React?" };
  if (command.name === "ask" && !rest) return { kind: "say", text: "Ask a question: /ask when is the demo?" };
  if (command.name === "task") {
    const [task = "", status = ""] = words;
    if (words.length !== 2 || !/^\d+$/.test(task) || !STATUSES.includes(status.toLowerCase())) {
      return { kind: "say", text: "Write the task's number in the plan and its new status: /task 2 done" };
    }
    return { kind: "task", task, status: status.toLowerCase() };
  }
  return { kind: "run", name: command.name, rest };
}

/** The suggestions under the message box while the member types "/..." or "@...". */
export function suggest(draft: string): { label: string; about: string; fill: string }[] {
  if (/^\/\S*$/.test(draft)) {
    const typed = draft.slice(1).toLowerCase();
    return COMMANDS.filter((c) => c.name.startsWith(typed)).map((c) => ({ label: c.hint, about: c.about, fill: `/${c.name} ` }));
  }
  const at = /(^|\s)(@\w*)$/.exec(draft);
  if (at && MENTION.startsWith(at[2]!.toLowerCase()) && at[2]!.toLowerCase() !== MENTION) {
    return [{ label: MENTION, about: "Ask Cadence directly", fill: draft.slice(0, draft.length - at[2]!.length) + MENTION + " " }];
  }
  return [];
}
