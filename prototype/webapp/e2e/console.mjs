// The console opens chat first (U1, 19 Nov): the plan is closed and the
// on-demand actions sit behind one "Ask Cadence" menu. Shared by the specs.

/** Open the plan beside the chat (no-op if it is already open). */
export async function openPlan(page) {
  const plan = page.getByRole("button", { name: "Plan", exact: true });
  if ((await plan.getAttribute("aria-expanded")) !== "true") await plan.click();
}

/** Run one action of the "Ask Cadence" menu by its label. */
export async function askCadence(page, label) {
  await page.getByRole("button", { name: "Ask Cadence" }).click();
  await page.getByRole("menuitem", { name: label }).click();
}
