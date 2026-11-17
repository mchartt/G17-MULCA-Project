// A new space, end to end on the offline stack: the three first steps tick off
// as they are done, the team shows the profile, the group picks the language,
// and an edited goal is a card that changes nothing until it is confirmed.
import { expect, test } from "@playwright/test";
import { signUp } from "./account.mjs";

const SHOTS = process.env.SHOTS_DIR;

test("first steps, team, language and an edited goal", async ({ browser }) => {
  const ada = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await ada.goto("/login");
  await signUp(ada, "Ada");
  await ada.locator("#c-project").fill("Group Steps");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "Group Steps" })).toBeVisible();

  // A new space says what comes first.
  const steps = ada.locator(".steps");
  await expect(steps.getByRole("listitem")).toHaveCount(3);
  await expect(steps.locator("[aria-current=step]")).toContainText("Fill in your profile");
  const team = ada.locator(".panel section", { hasText: "Team" });
  await expect(team).toContainText("No profile yet");
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/1-new-space.png` });

  // Step 1: the profile. It shows in the team and the step ticks off.
  await steps.getByRole("button", { name: "Add my profile" }).click();
  await ada.locator("#p-discipline").fill("Design");
  await ada.locator("#p-skills").fill("Figma, user research");
  await ada.locator("#p-hours").fill("6");
  await ada.getByRole("button", { name: "Save profile" }).click();
  await ada.getByRole("button", { name: "Close" }).click();
  await expect(team).toContainText("Design · Figma, user research · 6 h/week");
  await expect(steps.locator("[aria-current=step]")).toContainText("Paste the assignment");

  // The language of Cadence's texts is the group's choice.
  await ada.getByLabel("Cadence writes in").selectOption("it");
  await expect(ada.locator(".banner--info")).toContainText("Cadence now writes in Italian.");
  await expect(ada.getByLabel("Cadence writes in")).toHaveValue("it");

  // Step 2: the assignment, then the charter card.
  await steps.getByRole("button", { name: "Add the assignment" }).click();
  await ada.locator("#kickoff-text").fill("Build a coordinator. Demo on 2 December.");
  await ada.locator("dialog[open] button[type=submit]").click();
  const charter = ada.locator(".card", { hasText: "Project charter" }).first();
  await charter.getByRole("button", { name: "Confirm" }).click();
  await expect(steps.locator("[aria-current=step]")).toContainText("List your tasks");
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

  // Step 3: the tasks. With the three done, the list goes away.
  await steps.getByRole("button", { name: "Add the tasks" }).click();
  await ada.getByLabel("Tasks").fill("Server API\nUI screens");
  await ada.getByRole("button", { name: "Suggest owners" }).click();
  await ada.locator(".card", { hasText: "Plan: who does what" }).getByRole("button", { name: "Confirm" }).click();
  await expect(steps).toHaveCount(0);
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/4-all-done.png` });
});
