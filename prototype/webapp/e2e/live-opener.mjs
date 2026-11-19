// LIVE run of the plan opener (LIVE_RUN_PLAN_OPENER.md): three people in three
// browser contexts against the real stack (MUCA-Server + Azure, adapter on
// :8080). It spends Azure credit: run it only with Matteo's OK.
//   node e2e/live-opener.mjs <L1|L2|L3|L4> <folder for screenshots>
// L1 continues with L5 (CS5 after the window), L3 continues with L6 (Plan together).
import { chromium } from "@playwright/test";
import { signUp } from "./account.mjs";
import { askCadence } from "./console.mjs";

const [scenario, shots] = process.argv.slice(2);
const BASE = "http://127.0.0.1:8080";
const QUESTION = "How do you want to plan the work?";
const BRIEF =
  "Build a web app that coordinates student project groups. Deliverables: report, working prototype, 2-minute pitch video. Demo Madness on 2 December 2026.";
const t0 = Date.now();
const log = (what, extra = {}) => console.log(JSON.stringify({ s: Math.round((Date.now() - t0) / 1000), scenario, what, ...extra }));
const shot = async (page, name) => shots && (await page.screenshot({ path: `${shots}/${scenario}-${name}.png` }));

const browser = await chromium.launch();
const person = async (name) => {
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await page.goto(`${BASE}/login`);
  await signUp(page, name);
  return page;
};
const say = async (page, text) => {
  await page.getByLabel("Message to the group").fill(text);
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1500);
};
const agentBubbles = (page) => page.locator(".msg--agent").count();

try {
  const ada = await person("Ada");
  const bruno = await person("Bruno");
  const chiara = await person("Chiara");
  await ada.locator("#c-project").fill(`Live ${scenario}`);
  await ada.getByRole("button", { name: "Create the space" }).click();
  await ada.getByRole("heading", { name: `Live ${scenario}` }).waitFor();
  const code = (await ada.locator(".invite code").textContent()).trim();
  for (const p of [bruno, chiara]) {
    await p.locator("#j-code").fill(code);
    await p.getByRole("button", { name: "Join the space" }).click();
    await p.getByRole("heading", { name: `Live ${scenario}` }).waitFor();
  }
  log("space ready", { code });

  if (scenario === "L4") {
    // A plan started by hand before the charter: no question expected.
    await ada.getByRole("navigation", { name: "Quick actions" }).getByRole("button", { name: "Create a task" }).click();
    await ada.locator("dialog[open]").getByLabel("Name").fill("Build the API");
    await ada.locator("dialog[open]").getByRole("button", { name: "Add task" }).click();
    await ada.getByText("Task added: “Build the API”.").waitFor();
    log("task added by hand");
  }

  await askCadence(ada, "Paste the assignment");
  await ada.locator("#kickoff-text").fill(BRIEF);
  await ada.locator("dialog[open] button[type=submit]").click();
  const charter = bruno.locator(".card", { hasText: "Project charter" }).first();
  await charter.waitFor({ timeout: 90_000 });
  log("charter card");
  await charter.getByRole("button", { name: "Confirm" }).click();
  await bruno.locator(".card", { hasText: "Confirmed by" }).first().waitFor({ timeout: 20_000 });
  log("charter confirmed");

  const question = ada.locator(".msg--agent", { hasText: QUESTION });
  const asked = await question.waitFor({ timeout: 30_000 }).then(() => true, () => false);
  log(asked ? "question asked" : "no question");
  await shot(ada, "1-after-charter");
  if (scenario === "L4") process.exit(0);
  if (!asked) throw new Error("the question did not come");

  const before = await agentBubbles(ada);
  const answers = {
    L1: [
      [ada, "Let's split by area: I take the API and the server."],
      [bruno, "I'll do the dashboard and the slides."],
      [chiara, "Check-in every Monday after the lab, and we take decisions here in the chat."],
    ],
    L2: [
      [ada, "Everyone picks the tasks they want from a shared list."],
      [bruno, "I'd rather have one person assigning the tasks, otherwise nobody takes the boring ones."],
    ],
    L3: [[chiara, "Which font do we use for the report?"]],
  }[scenario];
  for (const [p, text] of answers) await say(p, text);
  const lastAnswer = Date.now();
  log("answers sent", { count: answers.length });

  // The card (or nothing): the window closes at least 60 s after the question.
  const card = ada.locator(".card").filter({ hasText: scenario === "L2" ? "Close the decision" : "How you plan the work" });
  const came = await card.first().waitFor({ timeout: 150_000 }).then(() => true, () => false);
  const agentReplies = (await agentBubbles(ada)) - before;
  log(came ? "card" : "no card", { secondsAfterLastAnswer: Math.round((Date.now() - lastAnswer) / 1000), agentRepliesToAnswers: agentReplies });
  await ada.waitForTimeout(1200);
  await shot(ada, "2-card");
  if (came) {
    const text = (await card.first().innerText()).replace(/\s+/g, " ");
    log("card text", { text: text.slice(0, 900) });
  }

  if (scenario === "L1" && came) {
    await card.first().getByRole("button", { name: "Confirm" }).click();
    await ada.locator(".card", { hasText: "Confirmed by Ada" }).last().waitFor({ timeout: 20_000 });
    await ada.getByRole("list", { name: "Pages" }).getByRole("button", { name: "Decisions" }).click();
    await shot(ada, "3-decisions");
    log("decision saved", { decisions: (await ada.getByRole("region", { name: "Decisions", exact: true }).innerText()).replace(/\s+/g, " ").slice(0, 300) });
    await ada.getByRole("list", { name: "Pages" }).getByRole("button", { name: "Chat" }).click();

    // L5: ordinary chat, then an agreed action with no owner. CS5 may step in now.
    const chat = [
      [bruno, "Ok, I'm starting the dashboard mockups today."],
      [chiara, "I'll look at the course slides for the report structure."],
      [ada, "The API skeleton is up, I'll push it tonight."],
      [bruno, "Nice, I can use fake data until then."],
      [chiara, "Do we meet on Monday at 14:00?"],
      [ada, "Yes, Monday 14:00 works."],
      [bruno, "Works for me too."],
      [chiara, "Someone has to write the user test plan before Thursday."],
      [ada, "Yes, we can't run the tests without it."],
      [bruno, "Agreed, it's needed for Thursday."],
      [chiara, "Ok, let's not forget it."],
    ];
    const cardsBefore = await ada.locator(".card").count();
    for (const [p, text] of chat) await say(p, text);
    const cs5 = ada.locator(".card", { hasText: "Owner and date" });
    const fired = await cs5.first().waitFor({ timeout: 90_000 }).then(() => true, () => false);
    log(fired ? "L5 CS5 card" : "L5 no CS5 card", { newCards: (await ada.locator(".card").count()) - cardsBefore });
    await shot(ada, "4-after-chat");
  }

  if (scenario === "L3") {
    // L6: Plan together on demand, in the same space.
    await askCadence(ada, "Plan together");
    const again = await ada.locator(".msg--agent", { hasText: QUESTION }).nth(1).waitFor({ timeout: 30_000 }).then(() => true, () => false);
    log(again ? "L6 asked again" : "L6 no question");
    if (again) {
      await say(ada, "Let's split by area: I take the API.");
      await say(bruno, "And a quick check-in every Monday.");
      const cardL6 = ada.locator(".card", { hasText: "How you plan the work" });
      const came6 = await cardL6.first().waitFor({ timeout: 150_000 }).then(() => true, () => false);
      log(came6 ? "L6 card" : "L6 no card");
      await ada.waitForTimeout(1200);
      await shot(ada, "5-plan-together");
    }
  }
} catch (err) {
  log("error", { message: String(err).slice(0, 300) });
  process.exitCode = 1;
} finally {
  await browser.close();
}
