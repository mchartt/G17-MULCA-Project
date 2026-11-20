import { render, screen, within } from "@testing-library/react";
import { AgentReply } from "../console/Chat";
import { inline, parseAgentText } from "./agentText";

test("a reply becomes paragraphs, a list and its sources, from plain text", () => {
  const text = "Nel piano due task aspettano qualcosa:\n- I **test di integrazione** aspettano le API\n- Il Design Document aspetta il RASD\nFonti: attività “Integration tests”, attività “Write the Design Document”.";
  const parsed = parseAgentText(text);
  expect(parsed.blocks.map((b) => b.kind)).toEqual(["paragraph", "list"]);
  expect(parsed.sources).toEqual({ label: "Fonti", text: "attività “Integration tests”, attività “Write the Design Document”." });
  const list = parsed.blocks[1]!;
  expect(list.kind === "list" && list.items[0]).toEqual([
    { text: "I ", bold: false },
    { text: "test di integrazione", bold: true },
    { text: " aspettano le API", bold: false },
  ]);
});

test("a simple answer stays one paragraph; an unpaired ** is left as written", () => {
  expect(parseAgentText("Il RASD scade il 24 novembre.")).toEqual({
    blocks: [{ kind: "paragraph", parts: [{ text: "Il RASD scade il 24 novembre.", bold: false }] }],
    sources: null,
  });
  expect(inline("2 ** 3")).toEqual([{ text: "2 ** 3", bold: false }]);
});

test("the bubble shows the list and the sources, and never turns model text into markup", () => {
  const { container } = render(
    <AgentReply text={"Ecco:\n- **Matías** consegna i dati <script>alert(1)</script>\n- <img src=x onerror=alert(1)>\nFrom: task “RASD”."} />,
  );
  const items = within(screen.getByRole("list")).getAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(within(items[0]!).getByText("Matías").tagName).toBe("STRONG");
  expect(container.querySelector("script, img")).toBeNull();
  expect(items[1]!).toHaveTextContent("<img src=x onerror=alert(1)>");
  expect(screen.getByText("From:")).toBeInTheDocument();
});
