/**
 * Full workspace test runner.
 *
 * Runs frontend type checks, Playwright browser tests (skipped outside CI when
 * neither PLAYWRIGHT_CHANNEL nor Playwright's Chromium binary is available),
 * backend type checks/tests, and desktop Go tests.
 */
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const npmCli = process.env.npm_execpath;
if (!npmCli) {
  console.error("Run this script through npm test.");
  process.exit(1);
}

function isCiEnvironment() {
  const ci = process.env.CI;
  return Boolean(ci) && !["0", "false"].includes(ci.toLowerCase());
}

function hasFrontendBrowser() {
  if (process.env.PLAYWRIGHT_CHANNEL) return true;
  const playwrightPath = require.resolve("@playwright/test", {
    paths: [path.resolve(__dirname, "..", "frontend")],
  });
  const { chromium } = require(playwrightPath);
  const executablePath = chromium.executablePath();
  return Boolean(executablePath) && fs.existsSync(executablePath);
}

function runTask(task) {
  const result = spawnSync(process.execPath, [npmCli, "run", task], { stdio: "inherit" });
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status ?? 1);
}

runTask("check:frontend");
if (!isCiEnvironment() && !hasFrontendBrowser()) {
  console.log(
    '[TEST] Skipping test:frontend: Playwright Chromium is not installed. Run "npm --prefix frontend exec -- playwright install chromium", set PLAYWRIGHT_CHANNEL, or run "npm run test:frontend" explicitly.',
  );
} else {
  runTask("test:frontend");
}
runTask("test:backend");
runTask("test:desktop");
