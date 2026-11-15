// M3 end to end on the offline stack (e2e/fake_stack.py): a strategy fires
// (scripted trigger in place of the intervention agent), the card reaches both
// members, Why? shows the messages behind it, and the first click updates the
// card for everyone and the plan. Not now silences instead.
import { expect, test, type Browser, type Page } from "@playwright/test";

async function space(browser: Browser, project: string): Promise<[Page, Page]> {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await ada.getByRole("link", { name: "Open your space" }).click();
  await ada.getByLabel("I have read this and I agree").check();
  await ada.locator("#c-name").fill("Ada");
  await ada.locator("#c-project").fill(project);
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: project })).toBeVisible();
  const code = (await ada.locator(".invite code").textContent())!.trim();
  const bruno = await (await browser.newContext()).newPage();
  await bruno.goto(`/?code=${code}`);
  await bruno.getByLabel("I have read this and I agree").check();
  await bruno.locator("#j-name").fill("Bruno");
  await bruno.getByRole("button", { name: "Join the space" }).click();
  await expect(bruno.locator(".members")).toContainText("Ada");
  await expect(ada.locator(".members")).toContainText("Bruno");
  return [ada, bruno];
}

async function say(page: Page, text: string) {
  await page.getByLabel("Message to the group").fill(text);
  await page.keyboard.press("Enter");
}

test("CS2: a simple task becomes a card; Why? explains it; I'll take it puts it in the plan", async ({ browser }) => {
  const [ada, bruno] = await space(browser, "Group CS2");
  await say(ada, "Arial or Helvetica?");
  await say(bruno, "Helvetica, and fix the font size too");

  const card = ada.locator(".card", { hasText: "One person can do this" });
  await expect(card).toContainText("Fix fonts and margins of the report");
  await expect(card).toContainText("Evaluation protocol");
  await expect(bruno.locator(".card", { hasText: "One person can do this" })).toBeVisible();

  // Why?: the strategy and the two real messages, copied by the server.
  await card.getByRole("button", { name: "Why?" }).click();
  const why = card.getByRole("region", { name: "Why the coordinator stepped in" });
  await expect(why).toContainText("one person can do alone");
  await expect(why).toContainText("Arial or Helvetica?");
  await expect(why).toContainText("Helvetica, and fix the font size too");

  // Nothing in the plan yet; Bruno takes it, both see it closed and in the plan.
  await bruno.locator(".card", { hasText: "One person can do this" }).getByRole("button", { name: "I'll take it" }).click();
  await expect(card.getByRole("status")).toHaveText("Confirmed");
  await expect(card.getByRole("button", { name: "I'll take it" })).toHaveCount(0);
  await expect(ada.locator(".panel")).toContainText("Fix fonts and margins of the report");
  await expect(ada.locator(".panel")).toContainText("Bruno");

  // Helpful: feedback only, counted by the server, the card stays confirmed.
  await card.getByRole("button", { name: "Helpful" }).click();
  await expect(card.locator(".card__thanks")).toHaveText("Thanks: noted as helpful (1 member so far).");
  await expect(card.locator(".card__status")).toHaveText("Confirmed");
});

test("CS3: the decision card has one button per option; the choice goes to the decision log", async ({ browser }) => {
  const [ada, bruno] = await space(browser, "Group CS3");
  await say(ada, "Think-aloud or SUS? We keep going round in circles");
  const card = bruno.locator(".card", { hasText: "Close the decision" });
  await expect(card).toContainText("Which usability test do we run?");
  await card.getByRole("button", { name: "Think-aloud" }).click();
  await expect(ada.locator(".card", { hasText: "Close the decision" }).getByRole("status")).toHaveText("Confirmed");
  await expect(ada.locator(".panel")).toContainText("Think-aloud");
});

test("Not now closes the card as silenced for 30 minutes and changes nothing", async ({ browser }) => {
  const [ada] = await space(browser, "Group Not now");
  await say(ada, "Which font do we use?");
  const card = ada.locator(".card", { hasText: "One person can do this" });
  await card.getByRole("button", { name: "Not now" }).click();
  await expect(card.getByRole("status")).toHaveText("Not now: silenced on this topic for 30 minutes");
  await expect(ada.locator(".panel")).not.toContainText("Fix fonts and margins of the report");
});
