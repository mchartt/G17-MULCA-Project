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

  await askCadence(ada, "Plan tasks");
  await ada.getByLabel("Task 1", { exact: true }).fill("Interview five students");
  await ada.getByLabel("Owner of task 1").selectOption({ label: "Bruno" });
  await ada.getByRole("button", { name: "Make the plan card" }).click();
  const plan = ada.locator(".card", { hasText: "Plan: who does what" });
  await expect(plan).toContainText("Ada listed the tasks with their owners.");
  await plan.getByRole("button", { name: "Confirm" }).click();
  await showPage(ada, "Tasks");
  const tasks = ada.getByRole("region", { name: "Tasks", exact: true });
  await expect(tasks).toContainText("Interview five students");
  await expect(tasks).toContainText("Bruno");

  // Edit tasks (Quick access): a task added by hand with nobody on it, then dated.
  await askCadence(ada, "Edit tasks");
  await ada.locator("dialog[open]").getByLabel("New task", { exact: true }).fill("Write the report"); // the open register, not the closed New task popup
  await ada.getByRole("button", { name: "Add task" }).click();
  await ada.getByLabel("Date of Write the report").fill("2030-12-01");
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/5-register.png` });
  await ada.locator("dialog[open]").getByRole("button", { name: "Close" }).click();
  await expect(tasks).toContainText("No owner");

  // Bruno sees it and takes it; Ada sees his name without doing anything.
  await showPage(bruno, "Tasks");
  await bruno.getByRole("button", { name: "Take Write the report" }).click();
  await expect(tasks).not.toContainText("No owner");

  // A milestone by hand, then the plan day by day.
  await showPage(ada, "Milestones");
  await ada.getByRole("button", { name: "New milestone" }).click();
  const milestone = ada.getByRole("dialog", { name: "New milestone" });
  await milestone.getByLabel("Name").fill("First draft");
  await milestone.getByLabel("Date (optional)").fill("2030-12-01");
  await milestone.getByRole("button", { name: "Add milestone" }).click();
  await expect(ada.getByRole("region", { name: "Milestones", exact: true })).toContainText("First draft");
  await askCadence(ada, "Day by day");
  const day = ada.locator(".agenda > li", { hasText: "First draft" });
  await expect(day).toContainText("Write the report");
  await expect(day).toContainText("Bruno");
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/6-day-by-day.png` });
  await ada.locator("dialog[open]").getByRole("button", { name: "Close" }).click();

  // Done from the Tasks page: the task moves to the Done group.
  await showPage(ada, "Tasks");
  await ada.getByRole("checkbox", { name: "Write the report: done" }).click();
  await expect(ada.getByRole("region", { name: /^Done/ })).toContainText("Write the report");
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/7-panel.png` });
});
