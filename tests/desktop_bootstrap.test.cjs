const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const ts = require("../desktop/frontend/node_modules/typescript");

const rawScript = readFileSync(
  path.join(__dirname, "../desktop/frontend/src/main.ts"),
  "utf8",
);
const script = ts
  .transpileModule(rawScript, {
    compilerOptions: { target: ts.ScriptTarget.ESNext },
  })
  .outputText
  .replace(/^import\s+[^;]+;\s*/gm, "")
  .replace(/^export\s+/gm, "");

function createPage() {
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
  const terminalLines = [];
  class MockTerminal {
    constructor() {}
    loadAddon() {}
    open() {}
    clear() {
      terminalLines.length = 0;
    }
    write(text) {
      terminalLines.push(text);
    }
    writeln(line) {
      terminalLines.push(line);
    }
  }
  class MockFitAddon {
    fit() {}
  }
  const eventHandlers = new Map();
  const Events = {
    On(name, cb) {
      eventHandlers.set(name, cb);
    },
  };
  const window = {
    addEventListener() {},
    setInterval() {},
    location: { href: "" },
  };

  vm.runInNewContext(script, {
    document,
    window,
    Date,
    String,
    Math,
    Terminal: MockTerminal,
    FitAddon: MockFitAddon,
    Events,
  });
  return { document, elements, terminalLines, eventHandlers, window };
}

test("desktop version references the root package manifest", () => {
  const root = path.join(__dirname, "..");
  const manifest = JSON.parse(
    readFileSync(path.join(root, "package.json"), "utf8"),
  );
  const lock = JSON.parse(
    readFileSync(path.join(root, "package-lock.json"), "utf8"),
  );
  const config = readFileSync(
    path.join(root, "desktop/build/config.yml"),
    "utf8",
  );
  assert.equal(manifest.version.startsWith("v"), false);
  assert.equal(lock.version, manifest.version);
  assert.equal(lock.packages[""].version, manifest.version);
  assert.match(config, new RegExp(`version:\\s*"${manifest.version}"`));
});

test("startup log is expanded by default", () => {
  const html = readFileSync(
    path.join(__dirname, "../desktop/frontend/index.html"),
    "utf8",
  );
  assert.match(html, /<details\b[^>]*\bid="diagnostics"[^>]*\bopen(?:\s|>)/);
  assert.match(html, /<div\b[^>]*\bid="terminal-container"/);
});

test("backend-log events write output to terminal", () => {
  const page = createPage();
  const handler = page.eventHandlers.get("backend-log");
  assert.ok(handler, "backend-log event handler should be registered");

  handler({ data: "Initializing engine...\n" });
  handler({ data: "Models loaded.\n" });
  assert.deepEqual(page.terminalLines, [
    "Initializing engine...\n",
    "Models loaded.\n",
  ]);
});

test("backend-ready event navigates to backend URL", () => {
  const page = createPage();
  const handler = page.eventHandlers.get("backend-ready");
  assert.ok(handler, "backend-ready event handler should be registered");

  handler({});
  assert.equal(page.window.location.href, "http://127.0.0.1:18888");
});

test("desktop host embeds bootstrap assets and configures dev script", () => {
  const manifest = JSON.parse(
    readFileSync(path.join(__dirname, "../package.json"), "utf8"),
  );
  const mainGo = readFileSync(
    path.join(__dirname, "../desktop/main.go"),
    "utf8",
  );
  const taskfile = readFileSync(
    path.join(__dirname, "../desktop/Taskfile.yml"),
    "utf8",
  );
  assert.equal(manifest.scripts["dev:desktop"], "wails3 task --dir desktop dev");
  assert.equal(manifest.scripts["build:desktop"], "wails3 task --dir desktop build");
  assert.match(mainGo, /\/\/go:embed all:frontend\/dist/);
  assert.match(mainGo, /AssetFileServerFS\(assets\)/);
  assert.match(taskfile, /APP_NAME:\s*"vcclient-forge"/);
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

test("Build delegates to npm tasks on all platforms without duplicating build commands", () => {
  for (const platform of ["win32", "linux", "darwin"]) {
    assert.deepEqual(runBuild(platform), [
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
  }
});

test("build stops when a component fails", () => {
  assert.throws(() => runBuild("win32", [{ status: 7 }]), /exit 7/);
  assert.throws(
    () => runBuild("win32", [{ error: new Error("Cannot spawn npm") }]),
    /exit 1/,
  );
});
