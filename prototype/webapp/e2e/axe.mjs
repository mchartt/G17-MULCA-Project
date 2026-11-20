import { chromium } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { signUp } from "./account.mjs";
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const report = async (name) => {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  console.log(name, "violations:", r.violations.length);
  for (const v of r.violations) console.log(" -", v.id, v.impact, v.nodes.length, v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | "));
};
await page.goto("http://127.0.0.1:8090/");
await page.waitForTimeout(1500);
await report("landing");
await signUp(page, "Ada");
await page.getByRole("button", { name: "New project" }).click(); // the setup desk, /login/new
await page.locator("#c-project").fill("AUI group 17");
await page.getByRole("button", { name: "Create the space" }).click();
await page.waitForTimeout(1200);
await page.getByRole("button", { name: "Paste the assignment" }).first().click();
await page.getByRole("textbox", { name: "Assignment" }).fill("Deliver by 2 Dec.");
await page.getByRole("button", { name: "Send to Cadence" }).click();
await page.waitForTimeout(2500);
await report("console with card");
// M3: a proactive card (scripted trigger on the offline stack) with Why? open.
await page.getByLabel("Message to the group").fill("Which font do we use?");
await page.keyboard.press("Enter");
await page.locator(".card", { hasText: "One person can do this" }).getByRole("button", { name: "Why?" }).click();
await page.waitForTimeout(800);
await report("console with proactive card and Why? open");
// M4: two tasks, Find owners, plan card confirmed.
for (const title of ["Server API", "UI screens"]) {
  await page.getByRole("button", { name: /^New task/ }).click();
  await page.getByRole("dialog", { name: "New task" }).getByLabel("Name").fill(title);
  await page.getByRole("dialog", { name: "New task" }).getByRole("button", { name: "Add task" }).click();
  await page.getByRole("dialog", { name: "New task" }).waitFor({ state: "hidden" });
}
await page.getByRole("button", { name: /^Find owners/ }).click();
await page.waitForTimeout(800); // let the dialog finish fading in
await report("Find owners dialog open");
await page.getByRole("button", { name: "Ask Cadence to propose owners" }).click();
await page.locator(".card", { hasText: "Plan: who does what" }).getByRole("button", { name: "Confirm" }).click();
// (A CS3 card would be vetoed here: R3/R4, the CS2 card was posted minutes ago.)
await page.waitForTimeout(1200);
await report("console with plan card and status selects");
await browser.close();
