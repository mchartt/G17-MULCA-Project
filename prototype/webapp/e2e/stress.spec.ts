// A space after weeks of use, on the offline stack: many messages (one with a
// very long URL), many long tasks, a member with a very long name, a long
// notice, a decision. At three widths, nothing may overflow its column or push
// the page sideways. SHOTS_DIR=... saves the screenshots for the visual review.
import { expect, test, type Page } from "@playwright/test";
import { signUp } from "./account.mjs";

const SHOTS = process.env.SHOTS_DIR;
const LONG_URL = `https://example.org/${"a-very-long-path-segment-".repeat(12)}end`;
const LONG_NAME = "Bartholomew-Maximilian-Fitzgerald-Smythe"; // 40 characters, one word

/** Every checked element fits its own box (1px tolerance), and the page does not scroll sideways. */
async function noOverflow(page: Page, where: string) {
  const report = await page.evaluate(() => {
    const out: string[] = [];
    const doc = document.documentElement;
    if (doc.scrollWidth > innerWidth + 1) out.push(`page ${doc.scrollWidth} > ${innerWidth}`);
    const selectors = [".console__main", ".console__bar", ".side", ".rail", ".page", ".chat__log", ".card", ".bubble", ".register__row", ".members li", ".room", ".console__notices"];
    for (const selector of selectors) {
      document.querySelectorAll<HTMLElement>(selector).forEach((el, i) => {
        if (el.offsetParent === null) return; // hidden
        if (el.scrollWidth > el.clientWidth + 1) out.push(`${selector}[${i}] ${el.scrollWidth} > ${el.clientWidth}`);
      });
    }
    return out;
  });
  expect(report, `overflow on ${where}`).toEqual([]);
  // A long notice never takes more than a few lines of the screen.
  const tallest = await page.evaluate(() => Math.max(0, ...[...document.querySelectorAll<HTMLElement>(".console__notices .banner")].map((b) => b.getBoundingClientRect().height)));
  expect(tallest, `notice height on ${where}`).toBeLessThanOrEqual(130);
}

const say = async (page: Page, text: string) => {
  await page.getByLabel("Message to the group").fill(text);
  await page.keyboard.press("Enter");
};

test("a busy space stays inside its columns at every width", async ({ browser }) => {
  test.setTimeout(150_000);
  const ada = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await ada.goto("/login");
  await signUp(ada, "Ada");
  await ada.getByRole("button", { name: "New project" }).click(); // the setup desk, /login/new
  await ada.locator("#c-project").fill("A group project with a rather long name that keeps going on and on");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await ada.locator(".invite code").waitFor();
  const code = (await ada.locator(".invite code").textContent())!.trim();

  // A teammate with a very long one-word name.
  const bart = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await bart.goto("/login");
  await signUp(bart, LONG_NAME);
  await bart.locator("#j-code").fill(code);
  await bart.getByRole("button", { name: "Join the space" }).click();
  await bart.locator(".invite code").waitFor();

  // Weeks of chat.
  for (let i = 1; i <= 30; i++) await say(i % 2 ? ada : bart, `Message ${i}: an ordinary update about the work, nothing special here.`);
  await say(bart, `Here is the link: ${LONG_URL}`);
  await say(ada, "Supercalifragilisticexpialidocious".repeat(6));
  // Many long tasks, added from the chat.
  for (let i = 1; i <= 25; i++) await say(ada, `/task add Task ${i}: write the complete evaluation protocol for the user study with every single detail included`);
  // A decision card (scripted trigger on the offline stack) and a long notice.
  await say(bart, "Think-aloud or SUS for the test?");
  await ada.locator(".card").last().waitFor({ timeout: 15_000 });
  await say(ada, "/help");
  await ada.waitForTimeout(800);

  for (const [width, height] of [[1440, 900], [1024, 768], [390, 844]] as const) {
    await ada.setViewportSize({ width, height });
    await ada.waitForTimeout(400);
    await noOverflow(ada, `chat at ${width}`);
    if (SHOTS) await ada.screenshot({ path: `${SHOTS}/stress-chat-${width}.png` });
    for (const page of ["Tasks", "Decisions", "Dependencies"]) {
      await ada.getByRole("list", { name: "Pages" }).getByRole("button", { name: page }).click();
      await ada.waitForTimeout(300);
      await noOverflow(ada, `${page} at ${width}`);
      if (SHOTS && page === "Tasks") await ada.screenshot({ path: `${SHOTS}/stress-tasks-${width}.png` });
    }
    await ada.getByRole("list", { name: "Pages" }).getByRole("button", { name: "Chat" }).click();
  }
});

test("Project settings renames the space for every member, and a member's profile opens in a popup", async ({ browser }) => {
  const ada = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await ada.goto("/login");
  await signUp(ada, "Ada");
  await ada.getByRole("button", { name: "New project" }).click(); // the setup desk, /login/new
  await ada.locator("#c-project").fill("Group settings");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await ada.locator(".invite code").waitFor();
  const code = (await ada.locator(".invite code").textContent())!.trim();
  const bruno = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await bruno.goto("/login");
  await signUp(bruno, "Bruno");
  await bruno.locator("#j-code").fill(code);
  await bruno.getByRole("button", { name: "Join the space" }).click();
  await bruno.locator(".invite code").waitFor();

  await ada.getByRole("button", { name: "Project settings" }).click();
  const settings = ada.getByRole("dialog", { name: "Project settings" });
  await settings.getByLabel("Name of the space").fill("AUI group 17");
  await settings.getByRole("button", { name: "Save name" }).click();
  await expect(settings.getByText("Name saved.")).toBeVisible();
  if (SHOTS) await ada.screenshot({ path: `${SHOTS}/settings.png` });
  await settings.getByRole("button", { name: "Close" }).click();
  // Bruno's open tab shows the new name without reloading.
  await expect(bruno.getByRole("heading", { level: 1, name: "AUI group 17" })).toBeVisible();

  await bruno.locator(".members").getByRole("button", { name: /Ada/ }).click();
  await expect(bruno.getByRole("dialog", { name: "Ada" })).toBeVisible();
  if (SHOTS) await bruno.screenshot({ path: `${SHOTS}/member.png` });
});
