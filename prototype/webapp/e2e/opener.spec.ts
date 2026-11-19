// The plan opener (CS-OPEN-01), end to end on the offline stack: the charter is
// confirmed, Cadence asks how the group wants to plan the work, two members
// answer, a card sums it up, a member confirms, the Decisions page shows it.
// SCRIPTED: the model's summary and the window's timing (3 s / 1.5 s) are the
// fake stack's; this proves the UI path, not the quality of the summary.
import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { signUp } from "./account.mjs";
import { askCadence } from "./console.mjs";

const SHOTS = process.env.SHOTS_DIR;

test("after the charter Cadence asks how you plan the work, and the answer becomes a decision", async ({ browser }) => {
  const ada = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await ada.goto("/login");
  await signUp(ada, "Ada");
  await ada.getByRole("button", { name: "New project" }).click(); // the setup desk, /login/new
  await ada.locator("#c-project").fill("Group Opener");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "Group Opener" })).toBeVisible();

  // The charter, from the brief; confirming it is what makes Cadence ask.
  await askCadence(ada, "Paste the assignment");
  await ada.locator("#kickoff-text").fill("Build a coordinator. Demo on 2 December.");
  await ada.locator("dialog[open] button[type=submit]").click();
  const charter = ada.locator(".card", { hasText: "Project charter" }).first();
  await charter.getByRole("button", { name: "Confirm" }).click();

  // The question arrives in the chat as Cadence's message.
  const question = ada.locator(".msg--agent", { hasText: "How do you want to plan the work?" });
  await expect(question).toBeVisible({ timeout: 10_000 });
  await ada.waitForTimeout(900); // the bubble fades in
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/opener-1-question.png` });

  await ada.getByLabel("Message to the group").fill("Let's split by area: I take the API.");
  await ada.keyboard.press("Enter");
  await ada.getByLabel("Message to the group").fill("And a check-in every Monday after the lab.");
  await ada.keyboard.press("Enter");

  const card = ada.locator(".card", { hasText: "How you plan the work" });
  await expect(card).toBeVisible({ timeout: 15_000 });
  await expect(card).toContainText("check-in every Monday after the lab");
  await ada.waitForTimeout(900); // the card's entrance animation, so axe reads the final colours
  const axe = await new AxeBuilder({ page: ada }).include(".card").withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(axe.violations.map((v) => v.id)).toEqual([]);
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/opener-2-card.png` });
  await card.getByRole("button", { name: "Confirm" }).click();
  await expect(card).toContainText("Confirmed by Ada");

  await ada.getByRole("list", { name: "Pages" }).getByRole("button", { name: "Decisions" }).click();
  const page = ada.getByRole("region", { name: "Decisions", exact: true });
  await expect(page).toContainText("How the group plans the work");
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/opener-3-decisions.png` });

  // "Plan together" asks again on demand (live run 19/11: the adapter refused the command).
  await ada.getByRole("list", { name: "Pages" }).getByRole("button", { name: "Chat" }).click();
  await askCadence(ada, "Plan together");
  await expect(ada.locator(".msg--agent", { hasText: "How do you want to plan the work?" })).toHaveCount(2, { timeout: 10_000 });
});
