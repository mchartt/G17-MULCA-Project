// The project brief written while creating a space (description + documents),
// handed to the console of that space. The console sends it to Cadence with
// the usual "kickoff" command once the socket is open: Cadence then proposes
// the goal, deliverables and milestones as a card the group confirms.
//
// sessionStorage, keyed by the space token: it lives only in this tab and is
// read once. If it is lost, nothing breaks: the "Paste the brief" step is there.

const KEY = "cadence.brief:";

export type BriefDocument = { name: string; text: string; truncated: boolean };

/** One text for the coordinator: the description first, then each document under its name. */
export function composeBrief(description: string, documents: BriefDocument[]): string {
  const parts = [description.trim()];
  for (const d of documents) parts.push(`--- Document: ${d.name}${d.truncated ? " (first part only)" : ""} ---\n${d.text.trim()}`);
  return parts.filter(Boolean).join("\n\n");
}

/** false when the browser refused to keep it (storage full or blocked): the caller says so. */
export function savePendingBrief(spaceToken: string, text: string): boolean {
  if (!text.trim()) return true;
  try {
    sessionStorage.setItem(KEY + spaceToken, text);
    return true;
  } catch {
    return false; // the member can paste the brief from the setup card
  }
}

/** The brief waiting for this space, removed as it is read (sent once). */
export function takePendingBrief(spaceToken: string): string | null {
  try {
    const text = sessionStorage.getItem(KEY + spaceToken);
    sessionStorage.removeItem(KEY + spaceToken);
    return text;
  } catch {
    return null;
  }
}
