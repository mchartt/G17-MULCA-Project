import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FirstSteps, firstSteps } from "./FirstSteps";

const onProfile = vi.fn();
const onBrief = vi.fn();
const base = { me: 1, inviteCode: "K7Q2M9XA", charterCard: null, onProfile, onBrief };
const steps = () => screen.getByRole("list");

beforeEach(() => localStorage.clear());

test("alone in a new space: step 1 brings the team in, with the invite link and the code", async () => {
  render(<FirstSteps state={{}} memberCount={1} {...base} />);
  expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Bring your team in" })).toBeInTheDocument();
  expect(screen.getByLabelText("Invite code K7Q2M9XA")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy invite link" })).toBeInTheDocument();
  // Inviting can wait: skipping moves on to the profile, which opens the profile form.
  await userEvent.click(screen.getByRole("button", { name: "I'll do it later" }));
  expect(screen.getByRole("heading", { name: "Your profile" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Add my profile" }));
  expect(onProfile).toHaveBeenCalled();
});

test("copying says so, and shows the link when the browser refuses", async () => {
  const writeText = vi.fn().mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error("denied"));
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
  render(<FirstSteps state={{}} memberCount={1} {...base} />);
  await userEvent.click(screen.getByRole("button", { name: "Copy invite link" }));
  expect(writeText).toHaveBeenCalledWith(`${location.origin}/login?code=K7Q2M9XA`);
  expect(screen.getByRole("status")).toHaveTextContent("The invite link is copied.");
  await userEvent.click(screen.getByRole("button", { name: "Copy code" }));
  expect(screen.getByRole("status")).toHaveTextContent(`${location.origin}/login?code=K7Q2M9XA`);
});

test("with teammates and a profile, the brief is next; the drop zone opens the assignment dialog", async () => {
  const state = { members: [{ member_id: 1, display_name: "Ada", discipline: "Design" }] };
  render(<FirstSteps state={state} memberCount={3} {...base} />);
  expect(screen.getByText("Step 3 of 4")).toBeInTheDocument();
  expect(steps()).toHaveTextContent("Team (done)");
  expect(steps()).toHaveTextContent("Profile (done)");
  await userEvent.click(screen.getByRole("button", { name: /Paste the brief or upload the file/ }));
  expect(onBrief).toHaveBeenCalled();
});

test("a charter card waiting in the chat makes the charter the current step", () => {
  const state = { members: [{ member_id: 1, display_name: "Ada", skills: ["Figma"] }] };
  render(<FirstSteps state={state} memberCount={2} {...base} charterCard="p1" />);
  expect(screen.getByRole("heading", { name: "Confirm the charter" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Show the card" })).toBeInTheDocument();
});

test("the card folds to the stepper line, and stays folded in this browser", async () => {
  const { unmount } = render(<FirstSteps state={{}} memberCount={1} {...base} />);
  await userEvent.click(screen.getByRole("button", { name: "Hide" }));
  expect(screen.queryByText("Step 1 of 4")).toBeNull();
  unmount();
  render(<FirstSteps state={{}} memberCount={1} {...base} />);
  expect(screen.queryByText("Step 1 of 4")).toBeNull();
  // Clicking a step opens the card on it.
  await userEvent.click(screen.getByRole("button", { name: /^Brief/ }));
  expect(screen.getByText("Step 3 of 4")).toBeInTheDocument();
});

test("nothing is shown before the state arrives, or once the charter is confirmed", () => {
  const { container, rerender } = render(<FirstSteps state={null} memberCount={1} {...base} />);
  expect(container).toBeEmptyDOMElement();
  rerender(<FirstSteps state={{ charter: { goal: "Ship it" } }} memberCount={1} {...base} />);
  expect(container).toBeEmptyDOMElement();
});

test("the profile step is about MY profile, and a name alone is not a profile", () => {
  const others = { members: [{ member_id: 2, display_name: "Bruno", skills: ["Python"] }, { member_id: 1, display_name: "Ada", discipline: " ", skills: [] }] };
  expect(firstSteps(others, 1).profile).toBe(false);
  expect(firstSteps(others, 2).profile).toBe(true);
  // A linked channel's member id arrives as text.
  expect(firstSteps({ members: [{ member_id: "900000000000000001", display_name: "Chiara", discipline: "CS" }] }, "900000000000000001").profile).toBe(true);
});
