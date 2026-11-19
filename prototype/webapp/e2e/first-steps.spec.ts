// A new space, end to end on the offline stack: it opens chat first with one
// skippable hint (invite, optional profile), the team shows the profile, the
// group picks the language, the assignment and the tasks come from "Ask
// Cadence", and an edited goal is a card that changes nothing until confirmed.
import { expect, test } from "@playwright/test";
import { signUp } from "./account.mjs";
import { askCadence, openPlan } from "./console.mjs";

const SHOTS = process.env.SHOTS_DIR;

test("first steps, team, language and an edited goal", async ({ browser }) => {
  const ada = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await ada.goto("/login");
  await signUp(ada, "Ada");
  await ada.locator("#c-project").fill("Group Steps");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "Group Steps" })).toBeVisible();

  // A new space opens on the chat: the plan is closed, one hint says who to bring in.
  await expect(ada.getByRole("button", { name: "Plan", exact: true })).toHaveAttribute("aria-expanded", "false");
  await expect(ada.locator(".console__panel")).toHaveCount(0);
  const steps = ada.locator(".hint");
  await expect(steps).toContainText("Bring your teammates in");
  await openPlan(ada);
  const team = ada.locator(".panel section", { hasText: "Team" });
  await expect(team).toContainText("No profile yet");
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/1-new-space.png` });

  // The profile (optional): it shows in the team and the hint stops offering it.
  await steps.getByRole("button", { name: "Add my profile" }).click();
  await ada.locator("#p-discipline").fill("Design");
  await ada.locator("#p-skills").fill("Figma, user research");
  await ada.locator("#p-hours").fill("6");
  await ada.getByRole("button", { name: "Save profile" }).click();
  await ada.getByRole("button", { name: "Close" }).click();
  await expect(team).toContainText("Design · Figma, user research · 6 h/week");
  await expect(steps.getByRole("button", { name: "Add my profile" })).toHaveCount(0);

  // The language of Cadence's texts is the group's choice.
  await ada.getByLabel("Cadence writes in").selectOption("it");
  await expect(ada.locator(".banner--info")).toContainText("Cadence now writes in Italian.");
  await expect(ada.getByLabel("Cadence writes in")).toHaveValue("it");

  // The assignment, from "Ask Cadence", then the charter card.
  await askCadence(ada, "Paste the assignment");
  await ada.locator("#kickoff-text").fill("Build a coordinator. Demo on 2 December.");
  await ada.locator("dialog[open] button[type=submit]").click();
  const charter = ada.locator(".card", { hasText: "Project charter" }).first();
  await charter.getByRole("button", { name: "Confirm" }).click();
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
  await ada.getByRole("button", { name: "Hide this hint" }).click();
  await expect(steps).toHaveCount(0);
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/4-all-done.png` });
});
