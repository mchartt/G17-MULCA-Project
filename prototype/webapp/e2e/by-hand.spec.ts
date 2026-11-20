// The plan edited by hand, end to end on the offline stack: a document for
// the assignment, tasks with owners chosen in the planning list, the register,
// the day-by-day view, a milestone, and a second member who takes a task.
import { expect, test } from "@playwright/test";
import { signUp } from "./account.mjs";
import { askCadence, showPage } from "./console.mjs";

const SHOTS = process.env.SHOTS_DIR;

test("documents, tasks and milestones by hand", async ({ browser }) => {
  const ada = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await ada.goto("/login");
  await signUp(ada, "Ada");
  await ada.getByRole("button", { name: "New project" }).click(); // the setup desk, /login/new
  await ada.locator("#c-project").fill("Group Hand");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "Group Hand" })).toBeVisible();
  const code = (await ada.locator(".invite code").textContent())!.trim();

  // The profile: skills as tags, a background in the member's own words.
  await ada.getByRole("button", { name: /^Your profile/ }).click();
  await ada.locator("#p-discipline").fill("Design");
  await ada.locator("#p-skills").fill("Figma");
  await ada.keyboard.press("Enter");
  await ada.locator("#p-skills").fill("user research");
  await ada.locator("#p-background").fill("Two years of user research at a museum.");
  await ada.getByRole("button", { name: "Save profile" }).click();
  await ada.getByRole("button", { name: "Close" }).click();
  // The sidebar's member row opens the profile as the group sees it.
  await ada.locator(".members__row", { hasText: "Ada" }).click();
  const member = ada.getByRole("dialog", { name: /^Ada/ });
  await expect(member).toContainText("Design");
  await expect(member.getByRole("list", { name: "Skills" })).toContainText("user research");
  await expect(member).toContainText("Two years of user research at a museum.");
  await member.getByRole("button", { name: "Close", exact: true }).click();

  // The assignment from a document: its text is read and stays editable.
  await askCadence(ada, "Paste the assignment");
  await ada.locator("#kickoff-file").setInputFiles({ name: "brief.txt", mimeType: "text/plain", buffer: Buffer.from("Build a coordinator.\nDemo on 2 December.") });
  await expect(ada.locator("#kickoff-text")).toHaveValue("Build a coordinator.\nDemo on 2 December.");
  await expect(ada.locator(".upload")).toContainText("Read from brief.txt");
  await ada.locator("dialog[open] button[type=submit]").click();
  await ada.locator(".card", { hasText: "Project charter" }).first().getByRole("button", { name: "Confirm" }).click();

  // Bruno joins; Ada plans with one owner chosen by hand, no model needed.
  const bruno = await (await browser.newContext()).newPage();
  await bruno.goto("/login");
  await signUp(bruno, "Bruno");
  await bruno.locator("#j-code").fill(code);
  await bruno.getByRole("button", { name: "Join the space" }).click();
  await expect(bruno.getByRole("heading", { name: "Group Hand" })).toBeVisible();

  // Ada adds a task by hand with Bruno as owner (New task in Quick access): no card, no model.
  await askCadence(ada, "New task");
  let popup = ada.getByRole("dialog", { name: "New task" });
  await popup.getByLabel("Name").fill("Interview five students");
  await popup.getByLabel("Owner").selectOption({ label: "Bruno" });
  await popup.getByRole("button", { name: "Add task" }).click();
  await showPage(ada, "Tasks");
  const tasks = ada.getByRole("region", { name: "Tasks", exact: true });
  await ada.getByRole("tab", { name: /^To do/ }).click();
  await expect(tasks).toContainText("Interview five students");
  await expect(tasks).toContainText("Bruno");

  // A second task with nobody on it, dated.
  await ada.getByRole("button", { name: "New task", exact: true }).click();
  popup = ada.getByRole("dialog", { name: "New task" });
  await popup.getByLabel("Name").fill("Write the report");
  await popup.getByLabel("Due date").fill("2030-12-01");
  await popup.getByRole("button", { name: "Add task" }).click();
  await expect(tasks).toContainText("Write the report");
  await expect(ada.getByRole("button", { name: "I'll take it: Write the report" })).toBeVisible();
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/5-tasks.png` });

  // Bruno sees it and takes it; Ada sees his name without doing anything.
  await showPage(bruno, "Tasks");
  await bruno.getByRole("tab", { name: /^To do/ }).click();
  await bruno.getByRole("button", { name: "I'll take it: Write the report" }).click();
  await expect(ada.getByRole("button", { name: "I'll take it: Write the report" })).toHaveCount(0);

  // A milestone by hand.
  await showPage(ada, "Milestones");
  await ada.getByRole("button", { name: "New milestone" }).click();
  const milestone = ada.getByRole("dialog", { name: "New milestone" });
  await milestone.getByLabel("Name").fill("First draft");
  await milestone.getByLabel("Date (optional)").fill("2030-12-01");
  await milestone.getByRole("button", { name: "Add milestone" }).click();
  await expect(ada.getByRole("region", { name: "Milestones", exact: true })).toContainText("First draft");

  // Done from the Tasks page: the task moves to Completed.
  await showPage(ada, "Tasks");
  await ada.getByRole("tab", { name: /^To do/ }).click();
  await ada.getByRole("checkbox", { name: "Write the report: done" }).click();
  await ada.getByRole("tab", { name: /^Completed/ }).click();
  await expect(ada.getByRole("tabpanel")).toContainText("Write the report");
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/7-panel.png` });
});
