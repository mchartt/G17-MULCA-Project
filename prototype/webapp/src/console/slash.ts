/**
 * Slash commands typed in the message box (spec 11.5): shortcuts for what the
 * buttons above the chat already do. A command is never posted to the group.
 *
 *   /planning                      opens the "Plan tasks" dialog
 *   /planning Server; UI; Slides   sends those tasks (one per line or ";")
 *   /checkin                       runs the check-in
 */
export type Slash =
  | { kind: "planning"; tasks: string }
  | { kind: "checkin" }
  | { kind: "unknown"; name: string };

export const SLASH_HELP = "Commands: /planning, /checkin.";

/** null when the text is an ordinary message. */
export function parseSlash(text: string): Slash | null {
  const match = /^\s*\/([a-z]+)(?:\s+([\s\S]*))?$/i.exec(text);
  if (!match) return null;
  const name = match[1]!.toLowerCase();
  const rest = (match[2] ?? "").trim();
  if (name === "planning") {
    const tasks = rest.split(/[\n;]/).map((line) => line.trim()).filter(Boolean).join("\n");
    return { kind: "planning", tasks };
  }
  if (name === "checkin") return { kind: "checkin" };
  return { kind: "unknown", name };
}
