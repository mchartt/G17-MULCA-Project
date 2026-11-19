// End to end on the offline stack (e2e/fake_stack.py): landing, create a space,
// a second member joins with the code, kickoff card, confirm, plan updates for both.
import { expect, test } from "@playwright/test";
import { signUp } from "./account.mjs";
import { askCadence, showPage } from "./console.mjs";

test("two members: create, join, kickoff card, confirm, plan", async ({ browser }) => {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await expect(ada.getByRole("heading", { name: "Cadence", level: 1 })).toBeAttached();
  await ada.getByRole("link", { name: "Open your space" }).click();

  await signUp(ada, "Ada");
  await ada.getByRole("button", { name: "New project" }).click(); // the setup desk, /login/new
  await ada.locator("#c-project").fill("AUI group 17");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "AUI group 17" })).toBeVisible();
  const code = (await ada.locator(".invite code").textContent())!.trim();
  expect(code).toMatch(/^[A-Z2-9]{10}$/);

  const bruno = await (await browser.newContext()).newPage();
  await bruno.goto(`/?code=${code}`);
  await signUp(bruno, "Bruno");
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

  // Kickoff from Quick access: the card appears for both.
  await askCadence(bruno, "Paste the assignment");
  await bruno.getByRole("textbox", { name: "Assignment" }).fill("Deliver the prototype by 2 December.");
  await bruno.getByRole("button", { name: "Send to Cadence" }).click();
  const card = ada.locator(".card", { hasText: "Project charter" });
  await expect(card).toContainText("Stepping in because");
  await expect(card.getByRole("status")).toHaveText("Waiting for a member to confirm");

  // Nothing changed yet; the first click applies it everywhere.
  await showPage(ada, "Decisions");
  await expect(ada.getByRole("region", { name: "Decisions", exact: true })).toContainText("No plan confirmed yet");
  await showPage(ada, "Chat");
  await card.getByRole("button", { name: "Confirm" }).click();
  await expect(bruno.locator(".card", { hasText: "Project charter" }).getByRole("status")).toHaveText(/^Confirmed by /);
  await showPage(bruno, "Decisions");
  await expect(bruno.locator(".registry__goal")).toHaveText("Ship the coordinator.");
  await expect(bruno.getByRole("region", { name: "Decisions", exact: true })).toContainText("Confirmed by Ada");
});
