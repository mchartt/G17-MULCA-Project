// Accessibility of the first minutes (WCAG 2.1 A/AA): landing, sign-up, the
// guided setup, a new project, the console with the tour, the registry and the
// Slack/Discord popup. Needs the offline stack running (python e2e/fake_stack.py).
import { chromium } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
let total = 0;
const report = async (name) => {
  await page.waitForTimeout(900); // let the entrance animations settle: axe reads the screen as the member sees it
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  total += r.violations.length;
  console.log(name, "violations:", r.violations.length);
  for (const v of r.violations) console.log(" -", v.id, v.impact, v.nodes.length, v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | "));
};
const base = "http://127.0.0.1:8090";

await page.goto(`${base}/`);
await page.waitForTimeout(1200);
// Every reveal shown, as after a full scroll.
await page.evaluate(() => document.querySelectorAll("[data-reveal]").forEach((el) => el.classList.add("is-in")));
await page.waitForTimeout(1000);
await report("landing");

await page.goto(`${base}/login`);
await report("login");
await page.locator("#a-name").fill("Ada");
await page.locator("#a-email").fill(`ada-axe-${Date.now()}@example.org`);
await page.locator("#a-password").fill("correct horse battery");
await page.getByLabel("I have read this and I agree").check();
await page.getByRole("button", { name: "Create my account" }).click();
await page.locator("#w-name").waitFor();
await report("welcome: name");
await page.getByRole("button", { name: /Continue/ }).click();
await report("welcome: background");
await page.getByRole("button", { name: /Continue/ }).click();
await page.locator("#w-skills").fill("Figma");
await page.keyboard.press("Enter");
await report("welcome: skills");
await page.getByRole("button", { name: /Save my profile/ }).click();
await page.getByRole("button", { name: /Create a project/ }).waitFor();
await page.waitForTimeout(800);
await report("welcome: ready");
await page.getByRole("button", { name: /Create a project/ }).click();
await page.locator("#c-project").fill("Axe onboarding");
await page.locator('input[type="file"]').setInputFiles([{ name: "brief.txt", mimeType: "text/plain", buffer: Buffer.from("Demo on 2 December.") }]);
await page.waitForTimeout(800);
await report("welcome: project with a document");
await page.getByRole("button", { name: "Create the space" }).click();
await page.locator(".tour").waitFor();
await page.waitForTimeout(800);
await report("console with the tour");
await page.getByRole("button", { name: "Skip tour" }).click();
await page.getByRole("list", { name: "Pages" }).getByRole("button", { name: "Decisions" }).click();
await report("decisions page");
await page.getByRole("list", { name: "Pages" }).getByRole("button", { name: "Tasks" }).click();
await report("tasks page");
await page.getByRole("button", { name: "Connect Slack or Discord" }).click();
await page.waitForTimeout(600);
await report("connect popup");
await browser.close();
console.log("total violations:", total);
process.exit(total ? 1 : 0);
