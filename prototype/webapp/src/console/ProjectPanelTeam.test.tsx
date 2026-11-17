import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProjectPanel } from "./ProjectPanel";

const members = [{ id: 1, name: "Ada" }, { id: 2, name: "Bruno" }];
const base = { members, onKickoff: vi.fn(), onRefresh: vi.fn() };

test("the team lists every member with what they wrote, and says when a profile is empty", async () => {
  const onProfile = vi.fn();
  render(
    <ProjectPanel
      {...base}
      me={2}
      onProfile={onProfile}
      state={{ members: [{ member_id: 1, display_name: "Ada", discipline: "Design", skills: ["Figma", "Research"], weekly_hours: 6 }] }}
    />,
  );
  const team = screen.getByRole("heading", { name: "Team" }).closest("section")!;
  const [bruno, ada] = within(team).getAllByRole("listitem"); // the viewer comes first
  expect(ada).toHaveTextContent("Design · Figma, Research · 6 h/week");
  expect(within(ada!).queryByRole("button")).toBeNull(); // nobody edits someone else's profile
  expect(bruno).toHaveTextContent("No profile yet");
  await userEvent.click(within(bruno!).getByRole("button", { name: "Fill in my profile" }));
  expect(onProfile).toHaveBeenCalled();
});

test("the group chooses the language Cadence writes in", async () => {
  const onLanguage = vi.fn();
  render(<ProjectPanel {...base} onLanguage={onLanguage} state={{ language: "it" }} />);
  const select = screen.getByLabelText("Cadence writes in");
  expect(select).toHaveValue("it");
  await userEvent.selectOptions(select, "English");
  expect(onLanguage).toHaveBeenCalledWith("en");
  await userEvent.selectOptions(select, "Follow the chat");
  expect(onLanguage).toHaveBeenLastCalledWith("");
});

test("the goal shows its deliverables and can be edited: the change is proposed, not saved", async () => {
  const onCharter = vi.fn().mockResolvedValueOnce("Nothing changed.").mockResolvedValueOnce(null);
  render(<ProjectPanel {...base} onCharter={onCharter} state={{ charter: { goal: "Ship it.", deliverables: ["Report", "Demo"], confirmed_by: 1 } }} />);
  expect(screen.getByText("Report")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Edit goal" }));
  const goal = screen.getByLabelText("Goal");
  expect(goal).toHaveValue("Ship it.");
  expect(screen.getByLabelText("Deliverables, one per line")).toHaveValue("Report\nDemo");

  await userEvent.click(screen.getByRole("button", { name: "Propose change" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Nothing changed."); // the server's words; the form stays open

  await userEvent.clear(goal);
  await userEvent.type(goal, "Ship the coordinator.");
  await userEvent.type(screen.getByLabelText("Deliverables, one per line"), "\n\n Video ");
  await userEvent.click(screen.getByRole("button", { name: "Propose change" }));
  expect(onCharter).toHaveBeenLastCalledWith("Ship the coordinator.", ["Report", "Demo", "Video"]);
  // Sent: the form closes and the goal is still the confirmed one, until the card is confirmed.
  expect(await screen.findByText("Ship it.")).toBeInTheDocument();
  expect(screen.queryByLabelText("Goal")).toBeNull();
});

test("without a way to edit, the goal has no edit button", () => {
  render(<ProjectPanel {...base} state={{ charter: { goal: "G" } }} />);
  expect(screen.queryByRole("button", { name: "Edit goal" })).toBeNull();
});
