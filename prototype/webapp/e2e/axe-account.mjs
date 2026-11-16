// Accessibility (WCAG 2.1 AA, axe) and screenshots of the account screens and
// the catch-up, on the offline stack:  node e2e/axe-account.mjs [folder for screenshots]
import { chromium } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { signUp } from "./account.mjs";

const shots = process.argv[2];
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: shots ? 2 : 1 });
const page = await context.newPage();
let failures = 0;

const report = async (name, selector) => {
  await page.waitForTimeout(900); // let fades finish: axe reads colours mid-animation otherwise
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  failures += r.violations.length;
  console.log(name, "violations:", r.violations.length);
  for (const v of r.violations) console.log(" -", v.id, v.impact, v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | "));
  if (shots) await (selector ? page.locator(selector) : page).screenshot({ path: `${shots}/${name}.png` });
};

await page.goto("http://127.0.0.1:8090/#enter");
await page.locator("#a-name").scrollIntoViewIfNeeded();
await report("account-register", "#enter");
await page.getByRole("tab", { name: "Log in" }).click();
await report("account-login", "#enter");

await signUp(page, "Ada");
await page.getByRole("button", { name: "My profile" }).click();
await page.locator("#p-discipline").fill("Interaction design");
await page.locator("#p-skills").fill("User research, prototyping");
await page.locator("#p-hours").fill("6");
await page.getByRole("button", { name: "Save profile" }).click();
await page.getByRole("status").filter({ hasText: "Profile saved" }).waitFor();
await report("account-profile", "#enter");
await page.getByRole("button", { name: "Close" }).click();

await page.locator("#c-project").fill("AUI group 17");
await page.getByRole("button", { name: "Create the space" }).click();
await page.getByRole("button", { name: "Catch up" }).click();
await page.getByText("/coordinator link").first().waitFor();
await report("console-catch-up");
await page.getByRole("button", { name: "Done" }).click();
await page.getByRole("button", { name: "Back to my spaces" }).click();
await page.getByRole("heading", { name: "Your spaces" }).scrollIntoViewIfNeeded();
await report("account-home", "#enter");

await browser.close();
process.exit(failures ? 1 : 0);
