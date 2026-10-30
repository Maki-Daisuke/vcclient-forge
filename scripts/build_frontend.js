/**
 * Frontend Build Stub / Synchronizer
 *
 * Copies web_front assets to frontend/dist and updates dist's version.txt and edition.txt.
 */
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const projectRoot = path.resolve(__dirname, "..");
const srcDir = path.join(projectRoot, "web_front");
const destDir = path.join(projectRoot, "frontend", "dist");

if (!fs.existsSync(srcDir)) {
  console.error(`[ERROR] Source directory does not exist: ${srcDir}`);
  process.exit(1);
}

// 1. Resolve version from package.json
const pkgPath = path.join(projectRoot, "package.json");
let version = "unknown";
if (fs.existsSync(pkgPath)) {
  try {
    const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
    if (pkg.version) version = pkg.version;
  } catch (err) {
    console.warn(`[WARN] Failed to parse package.json: ${err.message}`);
  }
}

// 2. Resolve edition from CLI args, env, or backend auto-detection
function parseEditionArg(args) {
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--edition" || args[i] === "-e") {
      return args[i + 1] || null;
    }
    if (args[i].startsWith("--edition=")) {
      return args[i].split("=")[1] || null;
    }
  }
  return null;
}

let edition = parseEditionArg(process.argv.slice(2)) || process.env.VCCLIENT_EDITION || process.env.EDITION || null;

if (!edition) {
  // Auto-detect from backend onnxruntime providers
  try {
    const uvBin = process.platform === "win32" ? "uv.exe" : "uv";
    const pyCode =
      "import onnxruntime as ort; p = ort.get_available_providers(); print('cuda' if 'CUDAExecutionProvider' in p else 'universal')";
    const res = spawnSync(uvBin, ["run", "--project", "backend", "python", "-c", pyCode], {
      cwd: projectRoot,
      encoding: "utf8",
      windowsHide: true,
    });
    if (res.status === 0 && res.stdout) {
      edition = res.stdout.trim();
    }
  } catch {
    // ignore
  }
}

if (!edition) {
  edition = "universal";
}

// 3. Sync web_front -> frontend/dist (source web_front remains untouched for git)
console.log(`[BUILD:FRONTEND] Syncing ${srcDir} -> ${destDir}...`);
fs.rmSync(destDir, { recursive: true, force: true });
fs.cpSync(srcDir, destDir, { recursive: true });

// 4. Write generated version.txt and edition.txt ONLY under frontend/dist UIs
const targetSettingsDirs = [
  path.join(destDir, "ui", "2.1.4", "assets", "gui_settings"),
  path.join(destDir, "ui", "2.0.78", "assets", "gui_settings"),
];

for (const dir of targetSettingsDirs) {
  if (fs.existsSync(path.dirname(dir))) {
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, "version.txt"), version, "utf8");
    fs.writeFileSync(path.join(dir, "edition.txt"), edition, "utf8");
  }
}

console.log(`[BUILD:FRONTEND] Injected version=${version}, edition=${edition} into dist UIs`);
console.log(`[OK] frontend/dist successfully prepared from web_front`);
