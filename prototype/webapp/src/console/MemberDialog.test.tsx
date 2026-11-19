// A teammate's profile in a popup (sidebar click): what they wrote, nothing computed about them.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemberDialog } from "./Dialogs";

HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };

const profile = { member_id: 2, display_name: "Bruno", discipline: "Interaction design", skills: ["Figma", "User research"], weekly_hours: 6, background: "Two years of UX work." };

test("a teammate's popup shows discipline, skills, hours and background, and no edit button", () => {
  render(<MemberDialog open member={{ id: 2, name: "Bruno" }} profile={profile} color="#0072B2" isMe={false} onEditProfile={vi.fn()} onClose={vi.fn()} />);
  const popup = screen.getByRole("dialog", { name: "Bruno" });
  expect(popup).toHaveTextContent("Interaction design");
  expect(screen.getByRole("list", { name: "Skills" })).toHaveTextContent("FigmaUser research");
  expect(popup).toHaveTextContent("6 h a week");
  expect(popup).toHaveTextContent("Two years of UX work.");
  expect(screen.queryByRole("button", { name: /Edit my profile/ })).toBeNull();
});

test("my own popup says (you), says when the profile is empty, and offers to edit it", async () => {
  const onEdit = vi.fn();
  render(<MemberDialog open member={{ id: 1, name: "Ada" }} profile={undefined} color="#B84E00" isMe onEditProfile={onEdit} onClose={vi.fn()} />);
  expect(screen.getByRole("dialog", { name: "Ada (you)" })).toHaveTextContent("No profile yet.");
  await userEvent.click(screen.getByRole("button", { name: /Edit my profile/ }));
  expect(onEdit).toHaveBeenCalled();
});
