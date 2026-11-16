// Limits closed after M5, end to end on the offline stack: "@coordinator why"
// typed in the chat is answered from the decision log, and "Delete space"
// removes the space for every member after typing its name.
import { expect, test, type Browser, type Page } from "@playwright/test";
import { signUp } from "./account.mjs";

async function create(browser: Browser, project: string): Promise<Page> {
  const ada = await (await browser.newContext()).newPage();
  await ada.goto("/");
  await ada.getByRole("link", { name: "Open your space" }).click();
  await signUp(ada, "Ada");
  await ada.locator("#c-project").fill(project);
  await ada.getByRole("button", { name: "Create the space" }).click();
  await expect(ada.getByRole("heading", { name: project })).toBeVisible();
  return ada;
}

test("@coordinator why, typed in the chat, is answered by Cadence from the decision log", async ({ browser }) => {
  const ada = await create(browser, "Group why");
  await ada.getByLabel("Message to the group").fill("@coordinator why did we pick SUS?");
  await ada.keyboard.press("Enter");
  await expect(ada.locator(".chat")).toContainText("No decision has been recorded yet.");
});

test("Delete space: only after typing the name; every member is sent back to the start", async ({ browser }) => {
  const ada = await create(browser, "Group delete");
  const code = (await ada.locator(".invite code").textContent())!.trim();
  const bruno = await (await browser.newContext()).newPage();
  await bruno.goto(`/?code=${code}`);
  await signUp(bruno, "Bruno");
  await bruno.getByRole("button", { name: "Join the space" }).click();
  await expect(bruno.locator(".members")).toContainText("Ada");

  await ada.getByRole("button", { name: "Delete this space" }).click();
  const dialog = ada.getByRole("dialog", { name: "Delete this space" });
  const confirm = dialog.getByRole("button", { name: "Delete everything" });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel(/to confirm/).fill("Group delete");
  await confirm.click();

  await expect(ada.getByRole("link", { name: "Open your space" })).toBeVisible();
  await expect(bruno.getByRole("link", { name: "Open your space" })).toBeVisible();
  // The invite code no longer opens anything.
  const again = await (await browser.newContext()).newPage();
  await again.goto(`/?code=${code}`);
  await signUp(again, "Eve");
  await again.getByRole("button", { name: "Join the space" }).click();
  await expect(again.getByRole("alert")).toContainText("No space uses this invite code");
});
