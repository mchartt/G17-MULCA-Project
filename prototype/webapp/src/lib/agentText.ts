// Cadence's chat replies, read as a few safe blocks (20/11, spec 4.3): short
// paragraphs, "- " lists, **bold**, and the last "From:" / "Fonti:" line kept
// apart as the sources. A pure function over plain text: no HTML is ever
// parsed, so nothing a model writes can become markup or a script.

export type Inline = { text: string; bold: boolean };
export type Block =
  | { kind: "paragraph"; parts: Inline[] }
  | { kind: "list"; items: Inline[][] };
export type AgentText = { blocks: Block[]; sources: { label: string; text: string } | null };

const SOURCES = /^(From|Fonti):\s*(.+)$/;
const ITEM = /^\s*(?:[-*•]|\d+[.)])\s+(.*)$/;

/** "a **b** c" -> [a, b(bold), c]; an unpaired "**" stays as written. */
export function inline(text: string): Inline[] {
  const pieces = text.split(/\*\*(.+?)\*\*/g);
  return pieces
    .map((piece, i) => ({ text: piece, bold: i % 2 === 1 }))
    .filter((p) => p.text !== "");
}

export function parseAgentText(raw: string): AgentText {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");
  let sources: AgentText["sources"] = null;
  // The sources line is the server's, always last.
  const last = lines.length ? lines[lines.length - 1]!.trim() : "";
  const found = SOURCES.exec(last);
  if (found) {
    sources = { label: found[1]!, text: found[2]! };
    lines.pop();
  }
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", parts: inline(paragraph.join(" ")) });
    paragraph = [];
  };
  for (const line of lines) {
    const item = ITEM.exec(line);
    if (item) {
      flush();
      const previous = blocks[blocks.length - 1];
      if (previous?.kind === "list") previous.items.push(inline(item[1]!));
      else blocks.push({ kind: "list", items: [inline(item[1]!)] });
    } else if (!line.trim()) {
      flush();
    } else {
      paragraph.push(line.trim());
    }
  }
  flush();
  return { blocks, sources };
}
