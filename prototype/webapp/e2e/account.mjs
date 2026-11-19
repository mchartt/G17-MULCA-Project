// Shared by the browser tests: create an account on the entry page. Each call
// uses a new email, so the tests can run again on the same offline stack.
let counter = 0;

export async function signUp(page, name) {
  counter += 1;
  const email = `${name.toLowerCase()}-${Date.now()}-${counter}@example.org`;
  await page.getByRole("tab", { name: "Create an account" }).click();
  await page.locator("#a-name").fill(name);
  await page.locator("#a-email").fill(email);
  await page.locator("#a-password").fill("correct horse battery");
  await page.getByLabel("I have read this and I agree").check();
  await page.getByRole("button", { name: "Create my account" }).click();
  // Logged in: the guided setup opens. These tests skip it (first-steps.spec walks it)
  // and have seen the console tour, so the home with "Start a new project" is there.
  await page.getByRole("button", { name: "Skip for now" }).click();
  await page.locator("#c-project").waitFor();
  await page.evaluate(() => localStorage.setItem("cadence:tour", "done"));
  return email;
}
