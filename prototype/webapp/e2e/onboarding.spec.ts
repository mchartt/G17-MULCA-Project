// The first minutes, end to end on the offline stack (e2e/fake_stack.py): the
// landing's story, sign-up, the guided profile, "your profile is set up", a
// project with its description and a document, then the console with the tour,
// the brief already sent to Cadence (its charter card in the chat), the quick
// actions and the plan and decision registry. SHOTS_DIR=... saves screenshots.
// The model is SCRIPTED here: this proves the UI path, not the quality of Cadence's answers.
import { expect, test } from "@playwright/test";

const SHOTS = process.env.SHOTS_DIR;
const shot = async (page, name: string) => {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` });
};

test("landing, guided setup, a project with a document, the tour and the registry", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });

  // The landing explains before it sells: what goes in, what Cadence notices, what comes out.
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Cadence keeps it moving.");
  await page.waitForTimeout(1400);
  await shot(page, "01-landing-hero");
  for (const [i, title] of ["You talk. Cadence listens.", "It notices what slips.", "You decide. Cadence remembers."].entries()) {
    await page.getByRole("heading", { name: title }).evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expect(page.locator(".flow__step.is-active")).toContainText(title);
    await page.waitForTimeout(900);
    await shot(page, `02-landing-step-${i + 1}`);
  }
  await page.locator(".guide").scrollIntoViewIfNeeded();
  await page.waitForTimeout(1000);
  await shot(page, "03-landing-guide");
  await page.locator(".rule").scrollIntoViewIfNeeded();
  await page.waitForTimeout(1000);
  await shot(page, "04-landing-rule");

  // Sign up: placeholders say what to write.
  await page.goto("/login");
  await expect(page.locator("#a-email")).toHaveAttribute("placeholder", "name@university.it");
  await page.locator("#a-name").fill("Sara");
  await page.locator("#a-email").fill(`sara-${Date.now()}@example.org`);
  await page.locator("#a-password").fill("correct horse battery");
  await page.getByLabel("I have read this and I agree").check();
  await shot(page, "05-signup");
  await page.getByRole("button", { name: "Create my account" }).click();

  // One question per screen.
  await expect(page.getByRole("heading", { name: "What should your group call you?" })).toBeVisible();
  await expect(page.locator("#w-name")).toHaveValue("Sara");
  await shot(page, "06-welcome-name");
  await page.getByRole("button", { name: /Continue/ }).click();
  await page.locator("#w-discipline").fill("Computer Science and Engineering");
  await page.locator("#w-background").fill("Two years of web development. I'd like to try user research.");
  await page.getByRole("button", { name: /Continue/ }).click();
  for (const skill of ["React", "Figma", "User interviews"]) {
    await page.locator("#w-skills").fill(skill);
    await page.keyboard.press("Enter");
  }
  await page.locator("#w-hours").fill("8");
  await shot(page, "07-welcome-skills");
  await page.getByRole("button", { name: /Save my profile/ }).click();
  await expect(page.getByRole("heading", { name: "Don't worry, your profile is set up." })).toBeVisible();
  await page.waitForTimeout(700);
  await shot(page, "08-welcome-ready");

  // A project: name, description, and a document shown as a sheet with its X.
  await page.getByRole("button", { name: /Create a project/ }).click();
  await page.locator("#c-project").fill("AUI group 17");
  await page.locator("#c-description").fill("Advanced User Interfaces, Politecnico di Milano. We build a group coordinator. Demo on 2 December, user tests the week before.");
  await page.locator('input[type="file"]').setInputFiles([
    { name: "assignment.txt", mimeType: "text/plain", buffer: Buffer.from("Deliver a working prototype by 2 December. Run a user test with 5 students.") },
    { name: "notes.md", mimeType: "text/markdown", buffer: Buffer.from("# Notes\nMarco: API. Sara: dashboard.") },
  ]);
  await expect(page.getByRole("list", { name: "Documents added" })).toContainText("assignment.txt");
  await page.waitForTimeout(700);
  await shot(page, "09-project-documents");
  await page.getByRole("button", { name: "Remove notes.md" }).click();
  await expect(page.getByRole("list", { name: "Documents added" })).not.toContainText("notes.md");
  await page.getByRole("button", { name: "Create the space" }).click();

  // The console: the tour starts, the brief is already with Cadence.
  await expect(page.getByRole("heading", { name: "AUI group 17" })).toBeVisible();
  const tour = page.getByRole("dialog", { name: "Talk to your group here" });
  await expect(tour).toBeVisible();
  await page.waitForTimeout(700);
  await shot(page, "10-tour-1");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForTimeout(600);
  await shot(page, "11-tour-3-quick-actions");
  await page.getByRole("button", { name: "Skip tour" }).click();
  await expect(page.locator(".tour")).toHaveCount(0);

  const charter = page.locator(".card", { hasText: "Project charter" }).first();
  await expect(charter).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(600);
  await shot(page, "12-console-brief-card");
  await charter.getByRole("button", { name: "Confirm" }).click();

  // Say hello to Cadence.
  await page.getByLabel("Message to the group").fill("@coordinator hello! How should we plan the work?");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1500);
  await shot(page, "13-console-chat");

  // The registry: the confirmed plan.
  await page.getByRole("list", { name: "Pages" }).getByRole("button", { name: "Decisions" }).click();
  await expect(page.getByRole("region", { name: "Decisions", exact: true })).not.toContainText("No plan confirmed yet");
  await shot(page, "14-decisions");
  await page.getByRole("list", { name: "Pages" }).getByRole("button", { name: "Tasks" }).click();
  await shot(page, "15-tasks");

  // Slack and Discord, explained.
  await page.getByRole("button", { name: "Connect Slack or Discord" }).click();
  await expect(page.getByRole("dialog", { name: "Connect Slack or Discord" })).toBeVisible();
  await page.waitForTimeout(500);
  await shot(page, "16-connect");
});

test("on a phone the landing reads top to bottom", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.waitForTimeout(1200);
  await shot(page, "17-mobile-hero");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
