// A new space, end to end on the offline stack: it opens chat first with the
// setup steps above it (team, profile, brief, charter; each skippable), the
// team shows the profile, the group picks the language, the brief becomes a
// charter card, the steps go once it is confirmed, an edited goal is a card
// that changes nothing until confirmed, and the tasks come from "Ask Cadence".
import { expect, test } from "@playwright/test";
import { signUp } from "./account.mjs";
import { askCadence, openPlan } from "./console.mjs";

const SHOTS = process.env.SHOTS_DIR;

test("first steps, team, language and an edited goal", async ({ browser }) => {
  const ada = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await ada.goto("/login");
  await signUp(ada, "Ada");
  await ada.getByRole("button", { name: "New project" }).click(); // the setup desk, /login/new
  await ada.locator("#c-project").fill("Group Steps");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "Group Steps" })).toBeVisible();

  // A new space opens on the chat: the plan is closed, the setup starts with the team.
  await expect(ada.getByRole("button", { name: "Plan", exact: true })).toHaveAttribute("aria-expanded", "false");
  await expect(ada.locator(".console__panel")).toHaveCount(0);
  const steps = ada.locator(".setup");
  await expect(steps).toContainText("Step 1 of 4");
  await expect(steps).toContainText("Bring your team in");
  await expect(steps.getByRole("button", { name: "Copy invite link" })).toBeVisible();
  await openPlan(ada);
  const team = ada.locator(".panel section", { hasText: "Team" });
  await expect(team).toContainText("No profile yet");
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/1-new-space.png` });

  // Inviting can wait; the profile (optional) shows in the team and the steps move on to the brief.
  await steps.getByRole("button", { name: "I'll do it later" }).click();
  await expect(steps).toContainText("Your profile");
  await steps.getByRole("button", { name: "Add my profile" }).click();
  await ada.locator("#p-discipline").fill("Design");
  await ada.locator("#p-skills").fill("Figma, user research");
  await ada.locator("#p-hours").fill("6");
  await ada.getByRole("button", { name: "Save profile" }).click();
  await ada.getByRole("button", { name: "Close" }).click();
  await expect(team).toContainText("Design · Figma, user research · 6 h/week");
  await expect(steps).toContainText("Paste the brief");

  // The language of Cadence's texts is the group's choice.
  await ada.getByLabel("Cadence writes in").selectOption("it");
  await expect(ada.locator(".banner--info")).toContainText("Cadence now writes in Italian.");
  await expect(ada.getByLabel("Cadence writes in")).toHaveValue("it");

  // The brief, from the setup step, then the charter card; confirming it ends the setup.
  await steps.getByRole("button", { name: /Paste the brief or upload the file/ }).click();
  await ada.locator("#kickoff-text").fill("Build a coordinator. Demo on 2 December.");
  await ada.locator("dialog[open] button[type=submit]").click();
  await expect(steps).toContainText("Confirm the charter");
  await steps.getByRole("button", { name: "Show the card" }).click();
  const charter = ada.locator(".card", { hasText: "Project charter" }).first();
  await charter.getByRole("button", { name: "Confirm" }).click();
  await expect(steps).toHaveCount(0);
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/2-after-charter.png` });

  // Editing the goal: a card; the panel keeps the confirmed goal until someone confirms.
  const goal = ada.locator(".panel section", { hasText: "Goal" }).first();
  const before = (await goal.locator(".panel__goal").textContent())!;
  await goal.getByRole("button", { name: "Edit goal" }).click();
  await ada.getByLabel("Goal").fill("Ship Cadence for the demo.");
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/3-goal-form.png` });
  await ada.getByRole("button", { name: "Propose change" }).click();
  const edit = ada.locator(".card", { hasText: "Ada edited the goal and deliverables." });
  await expect(edit).toContainText("Ship Cadence for the demo.");
  await expect(goal.locator(".panel__goal")).toHaveText(before);
  await edit.getByRole("button", { name: "Confirm" }).click();
  await expect(goal.locator(".panel__goal")).toHaveText("Ship Cadence for the demo.");

  // The tasks, from "Ask Cadence".
  await askCadence(ada, "Plan tasks");
  await ada.getByLabel("Task 1", { exact: true }).fill("Server API");
  await ada.getByLabel("Task 2", { exact: true }).fill("UI screens");
  await ada.getByRole("button", { name: "Suggest owners" }).click();
  await ada.locator(".card", { hasText: "Plan: who does what" }).getByRole("button", { name: "Confirm" }).click();
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/4-all-done.png` });
});
