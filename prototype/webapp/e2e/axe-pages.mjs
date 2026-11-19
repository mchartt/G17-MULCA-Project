// Accessibility of the left rail, its pages and the popups (19 Nov): WCAG 2.1 AA with axe.
// Needs the offline stack on :8090 running with the server that has task details.
import { chromium } from "@playwright/test";
import { AxeBuilder } from "@axe-core/playwright";
import { signUp } from "./account.mjs";

const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
let total = 0;
const report = async (name) => {
  await page.waitForTimeout(700); // let a dialog finish fading in
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  total += r.violations.length;
  console.log(name, "violations:", r.violations.length);
  for (const v of r.violations) console.log(" -", v.id, v.impact, v.nodes.length, v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | "));
};
const popup = page.locator("dialog[open]");
const fromMenu = async (what) => {
  await page.getByRole("navigation", { name: "Quick actions" }).getByRole("button", { name: `Create a ${what.toLowerCase()}` }).click();
};

await page.goto("http://127.0.0.1:8090/login");
await signUp(page, "Ada");
await page.locator("#c-project").fill("Axe pages");
await page.getByRole("button", { name: "Create the space" }).click();
await page.getByRole("heading", { name: "Axe pages" }).waitFor();
await report("chat with the rail");


await fromMenu("Task");
await popup.getByLabel("Name").fill("Build the API");
await report("New task popup (no other task)");
await popup.getByRole("button", { name: "Add task" }).click();
await popup.waitFor({ state: "detached" }).catch(() => {});
await fromMenu("Task");
await popup.getByLabel("Name").fill("Test the API");
await popup.getByLabel("Due date").fill("2020-01-01");
await popup.getByLabel("Build the API").check();
await report("New task popup (with waits on)");
await popup.getByRole("button", { name: "Add task" }).click();
await page.getByRole("button", { name: /^Today:/ }).click();
await report("Today popup");
await popup.getByRole("button", { name: "Close" }).click();

const rail = page.getByRole("list", { name: "Pages" });
await rail.getByRole("button", { name: "Dependencies" }).click();
await report("Dependencies page with the graph");
await page.getByRole("button", { name: "Link tasks" }).click();
await report("Link tasks popup");
await popup.getByRole("button", { name: "Cancel" }).click();

await rail.getByRole("button", { name: "Milestones" }).click();
await report("Milestones page (empty)");
await fromMenu("Milestone");
await popup.getByLabel("Name").fill("Prototype ready");
await report("New milestone popup");
await popup.getByRole("button", { name: "Add milestone" }).click();
await report("Milestones page with a group");

await rail.getByRole("button", { name: "Reflection" }).click();
await report("Reflection page");
await browser.close();
console.log(total === 0 ? "axe: 0 violations in total" : `axe: ${total} violations in total`);
process.exit(total === 0 ? 0 : 1);
