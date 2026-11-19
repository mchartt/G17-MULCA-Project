// The console opens chat first (U1, 19 Nov). The on-demand actions, the dates
// and the member's own shortcuts live in the Quick access panel on the right
// (open at desktop width, a sheet below 1100px). The plan lives on the left-hand
// pages. Shared by the specs.

/** Show Quick access if it is closed (a no-op at desktop width, where it opens beside the chat). */
export async function openQuick(page) {
  const toggle = page.getByRole("button", { name: "Quick access", exact: true });
  if ((await toggle.getAttribute("aria-expanded")) !== "true") await toggle.click();
}

/** Press one Quick access button by the start of its label ("Check-in", "Plan tasks", "Edit tasks"). */
export async function quick(page, label) {
  await openQuick(page);
  await page.getByRole("complementary", { name: "Quick access" }).getByRole("button", { name: new RegExp(`^${label}`) }).click();
}

/** The Ask Cadence group of Quick access: the same buttons, by label. */
export const askCadence = quick;

/** Open one page of the left rail: Chat, Tasks, Dependencies, Milestones, Decisions, Reflection. */
export async function showPage(page, name) {
  await page.getByRole("list", { name: "Pages" }).getByRole("button", { name, exact: true }).click();
}
