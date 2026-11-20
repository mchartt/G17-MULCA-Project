import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Chat } from "./Chat";
import { emptySpace, type Space } from "./space";

// jsdom has no layout, so no scrolling.
Element.prototype.scrollIntoView = vi.fn();

const noAnswer = async () => ({ type: "notice" as const, ok: true, text: "" });

function open(space: Space = emptySpace) {
  const onSay = vi.fn();
  const onCommand = vi.fn();
  render(<Chat space={space} onSay={onSay} onCommand={onCommand} onAnswer={noAnswer} disabled={false} />);
  return { onSay, onCommand, box: screen.getByLabelText("Message to the group") };
}

test("a line that starts with / runs as a command and is not sent to the group", async () => {
  const { onSay, onCommand, box } = open();
  await userEvent.type(box, "/checkin{Enter}");
  expect(onCommand).toHaveBeenCalledWith("/checkin");
  expect(onSay).not.toHaveBeenCalled();
});

test("an ordinary message is sent to the group", async () => {
  const { onSay, onCommand, box } = open();
  await userEvent.type(box, "@coordinator who takes the slides?{Enter}");
  expect(onSay).toHaveBeenCalledWith("@coordinator who takes the slides?");
  expect(onCommand).not.toHaveBeenCalled();
});

test("typing / lists the commands; Tab completes the first one", async () => {
  const { box } = open();
  await userEvent.type(box, "/pl");
  expect(screen.getByRole("list", { name: "Suggestions" })).toHaveTextContent("/planning");
  await userEvent.tab();
  expect(box).toHaveValue("/planning ");
});

test("typing @ offers the coordinator's tag", async () => {
  const { box } = open();
  await userEvent.type(box, "hi @");
  await userEvent.click(screen.getByRole("button", { name: /@coordinator/ }));
  expect(box).toHaveValue("hi @coordinator ");
});

test("@coordinator in a message is shown as a tag", () => {
  const ada = { id: 1, name: "Ada" };
  const space: Space = {
    ...emptySpace,
    me: ada,
    members: [ada],
    timeline: [{ kind: "message", message: { id: 1, author: ada, text: "@Coordinator help", channel: "web", ts: 0 } }],
  };
  open(space);
  expect(screen.getByText("@Coordinator")).toHaveClass("mention");
});

test("suggestions are chosen with the arrow keys; Enter completes a half-typed command and does not send it", async () => {
  const { onSay, onCommand, box } = open();
  await userEvent.type(box, "/c{ArrowDown}{Enter}"); // /checkin is first, /catchup second
  expect(box).toHaveValue("/catchup ");
  expect(onCommand).not.toHaveBeenCalled();
  await userEvent.type(box, "{Enter}");
  expect(onCommand).toHaveBeenCalledWith("/catchup ");
  await userEvent.type(box, "/pla{Tab}");
  expect((box as HTMLTextAreaElement).value.startsWith("/plan")).toBe(true);
  await userEvent.type(box, "{Escape}");
  expect(onSay).not.toHaveBeenCalled();
});

test("the empty chat says what Cadence does in plain words, without teaching @ or /", () => {
  open();
  expect(screen.getByText(/Talk normally\. Cadence reads along and steps in only when it notices a coordination gap/)).toBeInTheDocument();
  expect(screen.getByText(/Nothing changes until one of you clicks/)).toBeInTheDocument();
  expect(screen.queryByText(/Type \/ to see the commands/)).toBeNull();
});

test("while Cadence prepares an answer the chat says so, and its message clears the line", async () => {
  const { reduce } = await import("./space");
  let space = reduce({ ...emptySpace, agentName: "Cadence" }, { type: "typing", on: true });
  const { unmount } = render(<Chat space={space} onSay={vi.fn()} onCommand={vi.fn()} onAnswer={noAnswer} disabled={false} />);
  const line = screen.getByTestId("thinking");
  expect(line).toHaveAttribute("role", "status");
  expect(line.textContent).toMatch(/Cadence is thinking…|Cadence is cooking…|Let me see…|Cadence is looking at the plan…/);
  unmount();
  space = reduce(space, { type: "message", message: { id: 9, author: null, text: "Il dashboard è di Bruno.", channel: "web", at: 0 } as never });
  expect(space.thinking).toBe(false);
  // A member's message does not end it: Cadence is still working.
  const again = reduce(reduce(space, { type: "typing", on: true }), { type: "message", message: { id: 10, author: { id: 1, name: "Ada" }, text: "ok", channel: "web", at: 0 } as never });
  expect(again.thinking).toBe(true);
});
