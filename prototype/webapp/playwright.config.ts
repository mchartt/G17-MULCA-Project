import { defineConfig } from "@playwright/test";

// The offline stack is started by Playwright itself (see e2e/fake_stack.py).
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:8090", trace: "retain-on-failure" },
  webServer: {
    command: process.env.FAKE_STACK_CMD ?? "python e2e/fake_stack.py",
    url: "http://127.0.0.1:8090/api/session",
    reuseExistingServer: true,
    timeout: 60_000,
    stdout: "pipe",
    ignoreHTTPSErrors: true,
  },
});
