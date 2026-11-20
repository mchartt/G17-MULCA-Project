// The left rail and the quick actions, end to end on the offline stack: tasks
// and milestones made in popups, a dependency between two tasks (drawn and
// listed, on the jam board), Cadence's suggested link, a loop the server refuses, the reflection page.
// Needs the server with task details (description, depends_on): run the fake
// stack with it first on PYTHONPATH.
import { expect, test } from "@playwright/test";
import { signUp } from "./account.mjs";

const SHOTS = process.env.SHOTS_DIR;

// New task / New milestone are the buttons of their own pages (the right-hand panel has no copy of them).
async function newFromMenu(page, what: "Task" | "Milestone") {
  await page.getByRole("list", { name: "Pages" }).getByRole("button", { name: what === "Task" ? "Tasks" : "Milestones", exact: true }).click();
  await page.getByRole("button", { name: `New ${what.toLowerCase()}`, exact: true }).click();
}

test("quick actions, pages and dependencies", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/login");
  await signUp(page, "Ada");
  await page.getByRole("button", { name: "New project" }).click(); // the setup desk, /login/new
  await page.locator("#c-project").fill("Group Pages");
  await page.getByRole("button", { name: "Create the space" }).click();
  await expect(page.getByRole("heading", { name: "Group Pages" })).toBeVisible();

  // The chat is where the space opens; Quick access is beside it.
  const rail = page.getByRole("list", { name: "Pages" });
  await expect(rail.getByRole("button", { name: "Chat" })).toHaveAttribute("aria-current", "page");

  // A task in a popup: it closes, the banner says it is added.
  await newFromMenu(page, "Task");
  const popup = page.locator("dialog[open]");
  await popup.getByLabel("Name").fill("Build the API");
  await popup.getByLabel("Owner").selectOption({ label: "Ada" });
  await popup.getByRole("button", { name: "Add task" }).click();
  await expect(page.getByText("Task added: “Build the API”.")).toBeVisible();
  await expect(page.locator("dialog[open]")).toHaveCount(0);

  // A second task that waits on the first, with a description and a date already passed (so it is late today).
  await newFromMenu(page, "Task");
  await popup.getByLabel("Name").fill("Test the API");
  await popup.getByLabel("Description (optional)").fill("Run the contract tests");
  await popup.getByLabel("Due date").fill("2020-01-01");
  await popup.getByLabel("Build the API").check();
  await popup.getByRole("button", { name: "Add task" }).click();
  await expect(page.getByText("Task added: “Test the API”.")).toBeVisible();
  // Late today: the Tasks page shows it under Due soon, with "Late".
  await rail.getByRole("button", { name: "Tasks" }).click();
  await page.getByRole("tab", { name: /^Due soon\s*1/ }).click();
  await expect(page.getByRole("tabpanel")).toContainText("Late ·");

  // The dependency page: notes on the board and the same in words; the second task waits.
  await rail.getByRole("button", { name: "Dependencies" }).click();
  await expect(page.getByRole("button", { name: /^Test the API .*Change what it waits on$/ })).toBeVisible();
  const list = page.getByRole("region", { name: "In words" });
  await expect(list).toContainText("Test the API");
  await expect(list.getByText("Waiting")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/pages-1-dependencies.png` });

  // Removing the link by hand, then a loop: the server refuses and says why.
  await list.getByRole("button", { name: "Change what Test the API waits on" }).click();
  await popup.getByLabel("Build the API").uncheck();
  await popup.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Nothing waits on anything yet.")).toBeVisible();

  await page.getByRole("button", { name: "Link tasks" }).click();
  await popup.getByLabel("Task").selectOption({ label: "Test the API" });
  await popup.getByLabel("Build the API").check();
  await popup.getByRole("button", { name: "Save" }).click();
  await expect(list.getByText("Waiting")).toBeVisible();

  await page.getByRole("button", { name: "Link tasks" }).click();
  await popup.getByLabel("Task").selectOption({ label: "Build the API" });
  await popup.getByLabel("Test the API").check();
  await popup.getByRole("button", { name: "Save" }).click();
  await expect(popup.getByRole("alert")).toContainText("That would make a loop");
  await popup.getByRole("button", { name: "Cancel" }).click();

  // A milestone without a date waits to be scheduled, and moves up when it gets one.
  await rail.getByRole("button", { name: "Milestones" }).click();
  await newFromMenu(page, "Milestone");
  await popup.getByLabel("Name").fill("Prototype ready");
  await popup.getByRole("button", { name: "Add milestone" }).click();
  const toSchedule = page.getByRole("region", { name: /^To schedule/ });
  await expect(toSchedule).toContainText("Prototype ready");
  await toSchedule.getByLabel("Date of Prototype ready").fill("2099-12-01");
  await expect(page.getByRole("region", { name: /^To complete/ })).toContainText("Prototype ready");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/pages-2-milestones.png` });

  // A third task named "Test ...": Cadence suggests what it waits on (SCRIPTED), confirmed on the board.
  await newFromMenu(page, "Task");
  await popup.getByLabel("Name").fill("Test the slides");
  await popup.getByRole("button", { name: "Add task" }).click();
  await rail.getByRole("button", { name: "Dependencies" }).click();
  const ideas = page.getByRole("list", { name: "Cadence's suggestions" });
  await expect(ideas).toContainText("“Test the slides” waits on");
  await ideas.getByRole("button", { name: "Confirm" }).click();
  await expect(ideas).toBeHidden();

  // The reflection: the week in numbers, then back to the chat.
  await rail.getByRole("button", { name: "Reflection" }).click();
  await expect(page.getByRole("list", { name: "The week in numbers" })).toContainText("of the plan done");
  await rail.getByRole("button", { name: "Chat" }).click();
  await expect(page.getByRole("region", { name: "Group chat" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/pages-3-chat.png` });
});
