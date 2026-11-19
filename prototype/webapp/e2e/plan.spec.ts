// M4 end to end on the offline stack: /planning card, task status from the
// panel, check-in (findings computed by the server), "why did we decide X?".
import { expect, test } from "@playwright/test";
import { signUp } from "./account.mjs";
import { askCadence, showPage } from "./console.mjs";

test("planning, task status, check-in and why with source", async ({ browser }) => {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await ada.getByRole("link", { name: "Open your space" }).click();
  await signUp(ada, "Ada");
  await ada.locator("#c-project").fill("Group M4");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "Group M4" })).toBeVisible();

  // Check-in on an empty plan: on track, no card.
  await askCadence(ada, "Check-in");
  await expect(ada.locator(".banner--info")).toContainText("on track");

  // /planning: one card with owners and reasons; nothing in the plan before Confirm.
  await askCadence(ada, "Plan tasks");
  await ada.getByLabel("Task 1", { exact: true }).fill("Server API");
  await ada.getByLabel("Task 2", { exact: true }).fill("UI screens");
  await ada.getByRole("button", { name: "Suggest owners" }).click();
  const card = ada.locator(".card", { hasText: "Plan: who does what" });
  await expect(card).toContainText("Free hours this week.");
  await showPage(ada, "Tasks");
  await expect(ada.getByRole("region", { name: "Tasks", exact: true })).not.toContainText("Server API");
  await showPage(ada, "Chat");
  await card.getByRole("button", { name: "Confirm" }).click();
  await showPage(ada, "Tasks");
  await expect(ada.getByRole("region", { name: "Tasks", exact: true })).toContainText("Server API");

  // A member updates a status from Edit tasks (Quick access).
  await askCadence(ada, "Edit tasks");
  await ada.getByRole("combobox", { name: "Status of UI screens" }).selectOption("blocked");
  await expect(ada.getByRole("combobox", { name: "Status of UI screens" })).toHaveValue("blocked");
  await ada.locator("dialog[open]").getByRole("button", { name: "Close" }).click();
  await expect(ada.getByRole("region", { name: "Tasks", exact: true })).toContainText("Blocked or waiting");

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
  await askCadence(ada, "Ask why");
  await ada.getByLabel("Your question").fill("Why think-aloud?");
  await ada.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(ada.locator(".askwhy__answer")).toContainText("Source: “Which usability test do we run?” → Think-aloud (decided by Ada on");
});

test("calendar: a private feed link that a calendar app can read, revocable", async ({ browser }) => {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await ada.getByRole("link", { name: "Open your space" }).click();
  await signUp(ada, "Ada");
  await ada.locator("#c-project").fill("Group calendar");
  await ada.getByRole("button", { name: "Create the space" }).click();
  // The charter (fake model) has the milestone "Demo" on 2 Dec 2026.
  await askCadence(ada, "Paste the assignment");
  await ada.getByRole("textbox", { name: "Assignment" }).fill("Deliver by 2 December.");
  await ada.getByRole("button", { name: "Send to Cadence" }).click();
  await ada.locator(".card", { hasText: "Project charter" }).getByRole("button", { name: "Confirm" }).click();
  await showPage(ada, "Decisions");
  await expect(ada.locator(".registry__goal")).toBeVisible();

  await askCadence(ada, "Add to my calendar");
  await ada.getByRole("button", { name: "Create my link" }).click();
  const link = ada.getByLabel(/^Subscribe to this link/);
  const first = await link.inputValue();
  const feed = await ada.request.get(first);
  expect(feed.headers()["content-type"]).toContain("text/calendar");
  expect(await feed.text()).toContain("SUMMARY:Milestone: Demo");

  await ada.getByRole("button", { name: "Make a new link" }).click();
  await expect(link).not.toHaveValue(first);
  expect((await ada.request.get(first)).status()).toBe(404);
});
