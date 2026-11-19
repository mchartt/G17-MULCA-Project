import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AskMenu } from "./AskMenu";
import { faClipboardCheck, faFileLines } from "../lib/icons";

function setup() {
  const kickoff = vi.fn();
  const checkin = vi.fn();
  render(
    <AskMenu
      items={[
        { key: "kickoff", label: "Paste the assignment", about: "Goal and milestones.", icon: faFileLines, run: kickoff },
        { key: "checkin", label: "Check-in", about: "Plan against dates.", icon: faClipboardCheck, run: checkin },
      ]}
    />,
  );
  return { kickoff, checkin, button: screen.getByRole("button", { name: "Ask Cadence" }) };
}

test("the on-demand actions are closed behind one menu button", () => {
  const { button } = setup();
  expect(button).toHaveAttribute("aria-haspopup", "menu");
  expect(button).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("menu")).toBeNull();
});

test("opening the menu focuses the first item; an item runs its action and closes the menu", async () => {
  const { button, checkin } = setup();
  await userEvent.click(button);
  expect(button).toHaveAttribute("aria-expanded", "true");
  const items = screen.getAllByRole("menuitem");
  expect(items.map((i) => i.querySelector(".ask__label")?.textContent)).toEqual(["Paste the assignment", "Check-in"]);
  expect(items[0]).toHaveFocus();
  expect(items[1]).toHaveAccessibleName("Check-in Plan against dates.");
  await userEvent.click(screen.getByRole("menuitem", { name: /^Check-in/ }));
  expect(checkin).toHaveBeenCalledOnce();
  expect(screen.queryByRole("menu")).toBeNull();
  expect(button).toHaveFocus();
});

test("keyboard: arrows move, Escape closes and gives focus back", async () => {
  const { button, kickoff } = setup();
  button.focus();
  await userEvent.keyboard("{ArrowDown}");
  const items = screen.getAllByRole("menuitem");
  expect(items[0]).toHaveFocus();
  await userEvent.keyboard("{ArrowDown}");
  expect(items[1]).toHaveFocus();
  await userEvent.keyboard("{ArrowDown}");
  expect(items[0]).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).toBeNull();
  expect(button).toHaveFocus();
  expect(kickoff).not.toHaveBeenCalled();
});
