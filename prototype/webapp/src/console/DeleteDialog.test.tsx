import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DeleteDialog } from "./Dialogs";

test("Delete stays disabled until the exact space name is typed, then reports server errors", async () => {
  const onDelete = vi.fn().mockResolvedValue("The coordinator server could not delete the data. Nothing was deleted: try again later.");
  render(<DeleteDialog open spaceName="Team 17" onClose={vi.fn()} onDelete={onDelete} />);
  const button = screen.getByRole("button", { name: "Delete everything", hidden: true });
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/to confirm/, { selector: "input" }), "team 1");
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/to confirm/, { selector: "input" }), "7");
  expect(button).toBeEnabled();
  await userEvent.click(button);
  expect(onDelete).toHaveBeenCalledWith("team 17");
  expect(await screen.findByText(/Nothing was deleted/, {}, {})).toBeInTheDocument();
});
