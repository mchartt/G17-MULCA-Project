import { defineConfig } from "@playwright/test";

// The offline stack is started by Playwright itself (see e2e/fake_stack.py).
// FAKE_WEB_PORT moves it off 8090 (another worktree's stack may be there: with
// reuseExistingServer the tests would silently run against that other code).
const port = process.env.FAKE_WEB_PORT ?? "8090";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  webServer: {
    command: process.env.FAKE_STACK_CMD ?? "python e2e/fake_stack.py",
    url: `http://127.0.0.1:${port}/api/session`,
    reuseExistingServer: true,
    timeout: 60_000,
    stdout: "pipe",
    ignoreHTTPSErrors: true,
  },
});
