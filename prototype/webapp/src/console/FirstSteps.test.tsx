import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FirstSteps, firstSteps } from "./FirstSteps";

const onProfile = vi.fn();
const base = { me: 1, inviteCode: "K7Q2M9XA", onProfile };

test("alone in a new space: one hint to bring the teammates in, the profile is optional", async () => {
  render(<FirstSteps state={{}} memberCount={1} {...base} />);
  expect(screen.getByRole("heading", { name: "Bring your teammates in" })).toBeInTheDocument();
  expect(screen.getByText(/K7Q2M9XA/)).toBeInTheDocument();
  // No planning steps any more: the assignment and the tasks are in "Ask Cadence".
  expect(screen.queryByRole("button", { name: "Add the assignment" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Add the tasks" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Add my profile" }));
  expect(onProfile).toHaveBeenCalled();
});

test("with teammates and an empty profile, the hint only offers the profile; it can be hidden", async () => {
  render(<FirstSteps state={{ members: [{ member_id: 1, display_name: "Ada" }] }} memberCount={3} {...base} />);
  expect(screen.getByRole("heading", { name: "Help Cadence suggest owners" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Hide this hint" }));
  expect(screen.queryByRole("heading")).toBeNull();
});

test("nothing is shown before the state arrives, or with teammates and a profile", () => {
  const { container, rerender } = render(<FirstSteps state={null} memberCount={1} {...base} />);
  expect(container).toBeEmptyDOMElement();
  rerender(<FirstSteps state={{ members: [{ member_id: 1, display_name: "Ada", discipline: "Design" }] }} memberCount={2} {...base} />);
  expect(container).toBeEmptyDOMElement();
});

test("the profile step is about MY profile, and a name alone is not a profile", () => {
  const others = { members: [{ member_id: 2, display_name: "Bruno", skills: ["Python"] }, { member_id: 1, display_name: "Ada", discipline: " ", skills: [] }] };
  expect(firstSteps(others, 1).profile).toBe(false);
  expect(firstSteps(others, 2).profile).toBe(true);
  // A linked channel's member id arrives as text.
  expect(firstSteps({ members: [{ member_id: "900000000000000001", display_name: "Chiara", discipline: "CS" }] }, "900000000000000001").profile).toBe(true);
});
