// End to end on the offline stack (e2e/fake_stack.py): landing, create a space,
// a second member joins with the code, kickoff card, confirm, plan updates for both.
import { expect, test } from "@playwright/test";

test("two members: create, join, kickoff card, confirm, plan", async ({ browser }) => {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await expect(ada.getByRole("heading", { name: "Cadence", level: 1 })).toBeAttached();
  await ada.getByRole("link", { name: "Skip the film" }).click();

  await ada.getByLabel("I have read this and I agree").check();
  await ada.locator("#c-name").fill("Ada");
  await ada.locator("#c-project").fill("AUI group 17");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "AUI group 17" })).toBeVisible();
  const code = (await ada.locator(".invite code").textContent())!.trim();
  expect(code).toMatch(/^[A-Z2-9]{10}$/);

  const bruno = await (await browser.newContext()).newPage();
  await bruno.goto(`/?code=${code}`);
  await bruno.getByLabel("I have read this and I agree").check();
  await bruno.locator("#j-name").fill("Bruno");
  await bruno.getByRole("button", { name: "Join the space" }).click();
  await expect(bruno.locator(".members")).toContainText("Ada");
  await expect(ada.locator(".members")).toContainText("Bruno");
  await expect(bruno.locator(".members li", { hasText: "(you)" })).toContainText("Bruno");
  await expect(ada.locator(".members li", { hasText: "(you)" })).toContainText("Ada");

  // Chat reaches the other member; the agent's reply is labelled.
  await ada.getByLabel("Message to the group").fill("@coordinator hello team");
  await ada.keyboard.press("Enter");
  await expect(bruno.getByText("@coordinator hello team", { exact: true })).toBeVisible();
  await expect(bruno.locator(".msg--agent").first()).toContainText("Cadence");

  // Kickoff from the panel: the card appears for both.
  await bruno.getByRole("button", { name: "Paste the assignment" }).first().click();
  await bruno.getByRole("textbox", { name: "Assignment" }).fill("Deliver the prototype by 2 December.");
  await bruno.getByRole("button", { name: "Send to Cadence" }).click();
  const card = ada.locator(".card", { hasText: "Project charter" });
  await expect(card).toContainText("Stepping in because");
  await expect(card.getByRole("status")).toHaveText("Waiting for a member to confirm");

  // Nothing changed yet; the first click applies it everywhere.
  await expect(ada.locator(".panel")).toContainText("No goal yet");
  await card.getByRole("button", { name: "Confirm" }).click();
  await expect(bruno.locator(".card", { hasText: "Project charter" }).getByRole("status")).toHaveText("Confirmed");
  await expect(bruno.locator(".panel__goal")).toHaveText("Ship the coordinator.");
  await expect(bruno.locator(".panel")).toContainText("Confirmed by Ada");
});
