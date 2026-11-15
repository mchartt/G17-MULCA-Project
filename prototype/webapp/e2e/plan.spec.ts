// M4 end to end on the offline stack: /planning card, task status from the
// panel, check-in (findings computed by the server), "why did we decide X?".
import { expect, test } from "@playwright/test";

test("planning, task status, check-in and why with source", async ({ browser }) => {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await ada.getByRole("link", { name: "Open your space" }).click();
  await ada.getByLabel("I have read this and I agree").check();
  await ada.locator("#c-name").fill("Ada");
  await ada.locator("#c-project").fill("Group M4");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "Group M4" })).toBeVisible();

  // Check-in on an empty plan: on track, no card.
  await ada.getByRole("button", { name: "Check-in" }).click();
  await expect(ada.locator(".banner--info")).toContainText("on track");

  // /planning: one card with owners and reasons; nothing in the plan before Confirm.
  await ada.getByRole("button", { name: "Plan tasks" }).click();
  await ada.getByLabel("Tasks").fill("Server API\nUI screens");
  await ada.getByRole("button", { name: "Suggest owners" }).click();
  const card = ada.locator(".card", { hasText: "Plan: who does what" });
  await expect(card).toContainText("Free hours this week.");
  await expect(ada.locator(".panel")).not.toContainText("Server API");
  await card.getByRole("button", { name: "Confirm" }).click();
  await expect(ada.locator(".panel")).toContainText("Server API");

  // A member updates a status from the panel.
  await ada.getByRole("combobox", { name: "Status of UI screens" }).selectOption("blocked");
  await expect(ada.getByRole("combobox", { name: "Status of UI screens" })).toHaveValue("blocked");

  // Check-in now finds the blocked task and offers options computed from it.
  await ada.getByRole("button", { name: "Check-in" }).click();
  const check = ada.locator(".card", { hasText: "What is late or at risk" });
  await expect(check).toContainText("Blocked: “UI screens” (Ada).");
  await check.getByRole("button", { name: "Drop it: not essential" }).click();
  await expect(check.getByRole("status")).toHaveText("Confirmed");

  // A decision (CS3 on the fake stack), then "why?" cites it.
  await ada.getByLabel("Message to the group").fill("Think-aloud or SUS?");
  await ada.keyboard.press("Enter");
  await ada.locator(".card", { hasText: "Close the decision" }).getByRole("button", { name: "Think-aloud" }).click();
  await ada.getByLabel("Ask why the group decided something").fill("Why think-aloud?");
  await ada.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(ada.locator(".askwhy__answer")).toContainText("Source: “Which usability test do we run?” → Think-aloud (decided by Ada on");
});

test("calendar: a private feed link that a calendar app can read, revocable", async ({ browser }) => {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await ada.getByRole("link", { name: "Open your space" }).click();
  await ada.getByLabel("I have read this and I agree").check();
  await ada.locator("#c-name").fill("Ada");
  await ada.locator("#c-project").fill("Group calendar");
  await ada.getByRole("button", { name: "Create the space" }).click();
  // The charter (fake model) has the milestone "Demo" on 2 Dec 2026.
  await ada.getByRole("button", { name: "Paste the assignment" }).first().click();
  await ada.getByRole("textbox", { name: "Assignment" }).fill("Deliver by 2 December.");
  await ada.getByRole("button", { name: "Send to Cadence" }).click();
  await ada.locator(".card", { hasText: "Project charter" }).getByRole("button", { name: "Confirm" }).click();
  await expect(ada.locator(".panel__goal")).toBeVisible();

  await ada.getByRole("button", { name: "Add to my calendar" }).click();
  const first = await ada.locator("#calendar-url").inputValue();
  const feed = await ada.request.get(first);
  expect(feed.headers()["content-type"]).toContain("text/calendar");
  expect(await feed.text()).toContain("SUMMARY:Milestone: Demo");

  await ada.getByRole("button", { name: "Make a new link" }).click();
  await expect(ada.locator("#calendar-url")).not.toHaveValue(first);
  expect((await ada.request.get(first)).status()).toBe(404);
});
