import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FirstSteps, firstSteps } from "./FirstSteps";

const run = { onProfile: vi.fn(), onKickoff: vi.fn(), onPlanning: vi.fn() };

test("a new space shows the three steps and highlights the first", async () => {
  render(<FirstSteps state={{}} me={1} {...run} />);
  const steps = screen.getAllByRole("listitem");
  expect(steps.map((s) => within(s).getByRole("button").textContent?.trim())).toEqual(["Add my profile", "Add the assignment", "Add the tasks"]);
  expect(steps[0]).toHaveAttribute("aria-current", "step");
  await userEvent.click(screen.getByRole("button", { name: "Add the assignment" }));
  expect(run.onKickoff).toHaveBeenCalled();
});

test("a done step loses its button and the next one becomes the current step", () => {
  render(<FirstSteps state={{ members: [{ member_id: 1, display_name: "Ada", skills: ["React"] }], charter: { goal: "G" } }} me={1} {...run} />);
  const [profile, charter, plan] = screen.getAllByRole("listitem");
  expect(within(profile!).queryByRole("button")).toBeNull();
  expect(within(charter!).queryByRole("button")).toBeNull();
  expect(plan).toHaveAttribute("aria-current", "step");
  expect(within(plan!).getByRole("button", { name: "Add the tasks" })).toBeInTheDocument();
});

test("nothing is shown before the state arrives, or once the three steps are done", () => {
  const { container, rerender } = render(<FirstSteps state={null} me={1} {...run} />);
  expect(container).toBeEmptyDOMElement();
  rerender(
    <FirstSteps
      state={{ members: [{ member_id: 1, display_name: "Ada", discipline: "Design" }], charter: { goal: "G" }, tasks: [{ title: "T", status: "todo" }] }}
      me={1}
      {...run}
    />,
  );
  expect(container).toBeEmptyDOMElement();
});

test("the profile step is about MY profile, and a name alone is not a profile", () => {
  const others = { members: [{ member_id: 2, display_name: "Bruno", skills: ["Python"] }, { member_id: 1, display_name: "Ada", discipline: " ", skills: [] }] };
  expect(firstSteps(others, 1).profile).toBe(false);
  expect(firstSteps(others, 2).profile).toBe(true);
  // A linked channel's member id arrives as text.
  expect(firstSteps({ members: [{ member_id: "900000000000000001", display_name: "Chiara", discipline: "CS" }] }, "900000000000000001").profile).toBe(true);
});
