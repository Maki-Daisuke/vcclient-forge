const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const script = readFileSync(
  path.join(__dirname, "../src-tauri/bootstrap/bootstrap.js"),
  "utf8",
);

function createPage(invoke, logPosition = {}) {
  const elements = new Map();
  const document = {
    body: { dataset: {} },
    getElementById(identifier) {
      if (!elements.has(identifier)) {
        elements.set(identifier, {
          textContent: "",
          hidden: true,
          disabled: false,
          scrollTop: 0,
          scrollHeight: 0,
          clientHeight: 0,
          attributes: {},
          handlers: {},
          setAttribute(name, value) {
            this.attributes[name] = value;
          },
          addEventListener(name, handler) {
            this.handlers[name] = handler;
          },
        });
      }
      return elements.get(identifier);
    },
  };
  const window = { __TAURI__: { core: { invoke } }, setInterval() {} };
  Object.assign(document.getElementById("logs"), logPosition);
  vm.runInNewContext(script, { document, window, Date, String, Math });
  return { document, elements };
}

test("desktop version references the root package manifest", () => {
  const root = path.join(__dirname, "..");
  const manifest = JSON.parse(
    readFileSync(path.join(root, "package.json"), "utf8"),
  );
  const lock = JSON.parse(
    readFileSync(path.join(root, "package-lock.json"), "utf8"),
  );
  const config = JSON.parse(
    readFileSync(path.join(root, "src-tauri/tauri.conf.json"), "utf8"),
  );
  assert.equal(config.version, "../package.json");
  assert.equal(manifest.version.startsWith("v"), false);
  assert.equal(lock.version, manifest.version);
  assert.equal(lock.packages[""].version, manifest.version);
});

test("startup log is expanded by default", () => {
  const html = readFileSync(
    path.join(__dirname, "../src-tauri/bootstrap/index.html"),
    "utf8",
  );
  assert.match(html, /<details\b[^>]*\bid="diagnostics"[^>]*\bopen(?:\s|>)/);
});

test("startup state shows progress and keeps retry hidden", async () => {
  const page = createPage(async () => ({
    phase: "starting",
    message: "Loading models",
    logs: ["Loading"],
  }));
  await new Promise(setImmediate);
  assert.equal(
    page.elements.get("status-title").textContent,
    "Starting backend",
  );
  assert.equal(page.elements.get("message").textContent, "Loading models");
  assert.equal(page.elements.get("startup").attributes["aria-busy"], "true");
  assert.equal(page.elements.get("retry").hidden, true);
});

for (const [label, scrollTop, expected] of [
  ["at the bottom", 780, 1000],
  ["reading earlier logs", 100, 100],
]) {
  test(`startup log preserves scroll intent when ${label}`, async () => {
    const page = createPage(
      async () => ({
        phase: "starting",
        message: "Downloading",
        logs: ["Model: 50%"],
      }),
      { scrollTop, scrollHeight: 1000, clientHeight: 220 },
    );
    await new Promise(setImmediate);
    assert.equal(page.elements.get("logs").textContent, "Model: 50%");
    assert.equal(page.elements.get("logs").scrollTop, expected);
  });
}

test("failed startup exposes diagnostics and retry returns to waiting", async () => {
  let phase = "failed";
  const calls = [];
  const page = createPage(async (command) => {
    calls.push(command);
    if (command === "retry_backend") {
      phase = "starting";
      return;
    }
    return { phase, message: "<backend error>", logs: ["Port already in use"] };
  });
  await new Promise(setImmediate);
  assert.equal(page.document.body.dataset.phase, "failed");
  assert.equal(page.elements.get("retry").hidden, false);
  assert.equal(page.elements.get("message").textContent, "<backend error>");
  assert.equal(page.elements.get("logs").textContent, "Port already in use");
  await page.elements.get("retry").handlers.click();
  assert.equal(
    calls.filter((command) => command === "retry_backend").length,
    1,
  );
  assert.equal(page.elements.get("retry").hidden, true);
  assert.equal(page.elements.get("retry").disabled, false);
  assert.equal(page.document.body.dataset.phase, "starting");
});

test("IPC failure remains visible without an unhandled rejection", async () => {
  const page = createPage(async () => {
    throw new Error("IPC unavailable");
  });
  await new Promise(setImmediate);
  assert.equal(
    page.elements.get("status-title").textContent,
    "Desktop connection unavailable",
  );
  assert.match(page.elements.get("message").textContent, /IPC unavailable/);
  assert.equal(page.elements.get("startup").attributes["aria-busy"], "false");
});

test("only the embedded startup page receives explicitly scoped desktop commands", () => {
  const root = path.join(__dirname, "../src-tauri");
  const manifest = JSON.parse(
    readFileSync(path.join(__dirname, "../package.json"), "utf8"),
  );
  const config = JSON.parse(
    readFileSync(path.join(root, "tauri.conf.json"), "utf8"),
  );
  const capability = JSON.parse(
    readFileSync(path.join(root, "capabilities/bootstrap.json"), "utf8"),
  );
  assert.equal(manifest.scripts["dev:desktop"], "tauri dev --no-dev-server");
  assert.equal(config.build.frontendDist, "./bootstrap");
  assert.equal(config.build.devUrl, undefined);
  assert.equal(capability.local, true);
  assert.equal(capability.remote, undefined);
  assert.deepEqual(capability.permissions, [
    "allow-startup-status",
    "allow-retry-backend",
  ]);
});

function runBuild(platform, results = []) {
  const calls = [];
  const build = readFileSync(
    path.join(__dirname, "../scripts/build.js"),
    "utf8",
  );
  vm.runInNewContext(build, {
    require(name) {
      assert.equal(name, "node:child_process");
      return {
        spawnSync(executable, args) {
          calls.push([executable, ...args]);
          return results.shift() ?? { status: 0 };
        },
      };
    },
    process: {
      env: { npm_execpath: "npm-cli.js" },
      execPath: "node",
      argv: [
        "node",
        "build.js",
        "--edition",
        "cuda",
        "--python-version",
        "3.14",
      ],
      platform,
      exit(status) {
        throw new Error(`exit ${status}`);
      },
    },
    console,
  });
  return calls;
}

test("Windows build delegates to npm tasks without duplicating build commands", () => {
  assert.deepEqual(runBuild("win32"), [
    ["node", "npm-cli.js", "run", "build:frontend", "--"],
    ["node", "npm-cli.js", "run", "build:desktop", "--"],
    [
      "node",
      "npm-cli.js",
      "run",
      "build:backend",
      "--",
      "--edition",
      "cuda",
      "--python-version",
      "3.14",
    ],
  ]);
});

test("non-Windows builds retain the current backend-only desktop policy", () => {
  for (const platform of ["linux", "darwin"]) {
    assert.equal(runBuild(platform).length, 2);
  }
});

test("build stops when a component fails", () => {
  assert.throws(() => runBuild("win32", [{ status: 7 }]), /exit 7/);
  assert.throws(
    () => runBuild("win32", [{ error: new Error("Cannot spawn npm") }]),
    /exit 1/,
  );
});
