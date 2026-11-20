// M4 end to end on the offline stack: /planning card, task status from the
// panel, check-in (findings computed by the server), "why did we decide X?".
import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { signUp } from "./account.mjs";
import { askCadence, showPage } from "./console.mjs";

test("planning, task status, check-in and why with source", async ({ browser }) => {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await ada.getByRole("link", { name: "Open your space" }).click();
  await signUp(ada, "Ada");
  await ada.getByRole("button", { name: "New project" }).click(); // the setup desk, /login/new
  await ada.locator("#c-project").fill("Group M4");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "Group M4" })).toBeVisible();

  // Check-in on an empty plan: on track, no card.
  await askCadence(ada, "Check-in");
  await expect(ada.locator(".toast")).toContainText("on track");

  // Two tasks by hand, then Find owners: one card with owners and reasons; nobody owns them before Confirm.
  for (const title of ["Server API", "UI screens"]) {
    await askCadence(ada, "New task");
    const add = ada.getByRole("dialog", { name: "New task" });
    await add.getByLabel("Name").fill(title);
    await add.getByRole("button", { name: "Add task" }).click();
    await expect(add).toBeHidden();
  }
  await askCadence(ada, "Find owners");
  await ada.getByRole("dialog", { name: "Find owners" }).getByRole("button", { name: "Ask Cadence to propose owners" }).click();
  const card = ada.locator(".card", { hasText: "Plan: who does what" });
  await expect(card).toContainText("Free hours this week.");
  await showPage(ada, "Tasks");
  await ada.getByRole("tab", { name: /^To do/ }).click();
  await expect(ada.getByRole("button", { name: "I'll take it: Server API" })).toBeVisible();
  await showPage(ada, "Chat");
  await card.getByRole("button", { name: "Confirm" }).click();
  await showPage(ada, "Tasks");
  await ada.getByRole("tab", { name: /^To do/ }).click();
  await expect(ada.getByRole("button", { name: /^I'll take it/ })).toHaveCount(0);

  // A member marks a task blocked from its details.
  await ada.getByRole("button", { name: /^UI screens .*Open the details$/ }).click();
  const details = ada.getByRole("dialog", { name: "Task details" });
  await details.getByLabel("Status").selectOption("blocked");
  await details.getByRole("button", { name: "Save" }).click();
  await expect(ada.getByRole("tabpanel")).toContainText("Blocked");

  // Check-in now finds the blocked task and offers options computed from it.
  await showPage(ada, "Chat");
  await askCadence(ada, "Check-in");
  const check = ada.locator(".card", { hasText: "What is late or at risk" });
  await expect(check).toContainText("Blocked: “UI screens” (Ada).");
  await check.getByRole("button", { name: "Drop it: not essential" }).click();
  await expect(check.getByRole("status")).toHaveText("Confirmed by Ada");

  // A decision (CS3 on the fake stack), then "why?" cites it.
  await ada.getByLabel("Message to the group").fill("Think-aloud or SUS?");
  await ada.keyboard.press("Enter");
  await ada.locator(".card", { hasText: "Close the decision" }).getByRole("button", { name: "Think-aloud" }).click();
  // Asking Cadence by name, in the chat (SCRIPTED answer on the offline stack).
  await ada.getByLabel("Message to the group").fill("Cadence, why think-aloud?");
  await ada.keyboard.press("Enter");
  await expect(ada.locator(".msg--agent", { hasText: "SCRIPTED answer to: why think-aloud?" })).toBeVisible();
});

test("calendar: Add to my calendar saves a file a calendar app can import", async ({ browser }) => {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await ada.getByRole("link", { name: "Open your space" }).click();
  await signUp(ada, "Ada");
  await ada.getByRole("button", { name: "New project" }).click(); // the setup desk, /login/new
  await ada.locator("#c-project").fill("Group calendar");
  await ada.getByRole("button", { name: "Create the space" }).click();
  // The charter (fake model) has the milestone "Demo" on 2 Dec 2026.
  await askCadence(ada, "Paste the assignment");
  await ada.getByRole("textbox", { name: "Assignment" }).fill("Deliver by 2 December.");
  await ada.getByRole("button", { name: "Send to Cadence" }).click();
  await ada.locator(".card", { hasText: "Project charter" }).getByRole("button", { name: "Confirm" }).click();
  await showPage(ada, "Decisions");
  await expect(ada.locator(".goal-card__text")).toBeVisible();

  const download = ada.waitForEvent("download");
  await askCadence(ada, "Add to my calendar");
  const file = await download;
  expect(file.suggestedFilename()).toBe("group-calendar.ics");
  const text = readFileSync(await file.path(), "utf8");
  expect(text).toContain("BEGIN:VCALENDAR");
  expect(text).toContain("SUMMARY:Milestone: Demo");
  await expect(ada.locator(".toast")).toContainText("Calendar file saved");
});
