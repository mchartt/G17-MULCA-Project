// "Cadence is thinking…" while an answer is prepared (SCRIPTED delay on the
// offline stack), seen by every member, gone when the answer arrives, and
// with no accessibility violation in the chat while it shows.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { signUp } from "./account.mjs";

test("a sure call shows Cadence thinking to the group until its answer is in the chat; axe finds nothing", async ({ browser }) => {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await ada.getByRole("link", { name: "Open your space" }).click();
  await signUp(ada, "Ada");
  await ada.getByRole("button", { name: "New project" }).click();
  await ada.locator("#c-project").fill("Group thinking");
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: "Group thinking" })).toBeVisible();

  await ada.getByLabel("Message to the group").fill("@coordinator take your time: who does the slides?");
  await ada.keyboard.press("Enter");
  const line = ada.getByTestId("thinking");
  await expect(line).toBeVisible();
  await expect(line).toHaveAttribute("role", "status");
  await expect(line).toContainText(/thinking…|cooking…|Let me see…|looking at the plan…/);

  const scan = await new AxeBuilder({ page: ada })
    .include(".chat")
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(scan.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);

  await expect(ada.locator(".chat")).toContainText("SCRIPTED answer to: take your time: who does the slides?");
  await expect(line).toHaveCount(0);
});
