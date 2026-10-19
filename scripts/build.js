const { spawnSync } = require("node:child_process");

const npmCli = process.env.npm_execpath;
if (!npmCli) {
  console.error("Run this script through npm run build.");
  process.exit(1);
}

const tasks = ["build:frontend"];
if (process.platform === "win32") tasks.push("build:desktop");
tasks.push("build:backend");

for (const task of tasks) {
  const args = task === "build:backend" ? process.argv.slice(2) : [];
  const result = spawnSync(process.execPath, [npmCli, "run", task, "--", ...args], { stdio: "inherit" });
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  if (result.status !== 0) process.exit(result.status ?? 1);
}