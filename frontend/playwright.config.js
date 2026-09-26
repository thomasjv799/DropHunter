import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://127.0.0.1:8082", browserName: "chromium" },
  webServer: {
    command:
      "cd .. && python -m flask --app 'web.app:create_app()' run --port 8082",
    url: "http://127.0.0.1:8082/healthz",
    reuseExistingServer: !process.env.CI,
  },
});
