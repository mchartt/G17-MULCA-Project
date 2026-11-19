import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { GoalForm } from "./Dialogs";

test("the goal form starts from the confirmed goal; saving proposes the change and closes only when it was sent", async () => {
  const onSave = vi.fn().mockResolvedValueOnce("Nothing changed.").mockResolvedValueOnce(null);
  const onClose = vi.fn();
  render(<GoalForm goal="Ship it." deliverables={["Report", "Demo"]} onSave={onSave} onClose={onClose} />);
  const goal = screen.getByLabelText("Goal");
  expect(goal).toHaveValue("Ship it.");
  expect(screen.getByLabelText("Deliverables, one per line")).toHaveValue("Report\nDemo");

  await userEvent.click(screen.getByRole("button", { name: "Propose change" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Nothing changed."); // the server's words; the form stays open
  expect(onClose).not.toHaveBeenCalled();

  await userEvent.clear(goal);
  await userEvent.type(goal, "Ship the coordinator.");
  await userEvent.type(screen.getByLabelText("Deliverables, one per line"), "\n\n Video ");
  await userEvent.click(screen.getByRole("button", { name: "Propose change" }));
  expect(onSave).toHaveBeenLastCalledWith("Ship the coordinator.", ["Report", "Demo", "Video"]);
  expect(onClose).toHaveBeenCalledTimes(1);
});
