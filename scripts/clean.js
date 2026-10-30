/**
 * VCClient Forge - Workspace Cleaner
 *
 * Cleans build artifacts, virtual environments, caches, and downloaded assets
 * for a completely fresh build and test environment.
 */
const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");

const targets = [
  "dist",
  "build",
  "desktop/bin",
  "backend/.venv",
  ".venv",
  "frontend/dist",
  "modules",
  "backend/.pytest_cache",
  "backend/.ruff_cache",
];

function cleanPath(relPath) {
  const fullPath = path.join(projectRoot, relPath);
  if (fs.existsSync(fullPath)) {
    try {
      console.log(`[CLEAN] Removing: ${relPath}`);
      fs.rmSync(fullPath, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
    } catch (err) {
      console.error(`\n[ERROR] Failed to remove ${relPath}: ${err.message}`);
      console.error(`[HINT] The file or directory may be in use by another process (e.g. running Python, Language Server, or editor).`);
      console.error(`       Please stop any running processes and try again.\n`);
      process.exit(1);
    }
  }
}

function cleanPyCache(dir) {
  if (!fs.existsSync(dir)) return;
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "__pycache__") {
          try {
            console.log(`[CLEAN] Removing pycache: ${path.relative(projectRoot, fullPath)}`);
            fs.rmSync(fullPath, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 });
          } catch (err) {
            console.error(`\n[ERROR] Failed to remove pycache ${fullPath}: ${err.message}`);
            process.exit(1);
          }
        } else {
          cleanPyCache(fullPath);
        }
      }
    }
  } catch (err) {
    // Ignore unreadable dirs
  }
}

console.log("==========================================");
console.log(" Cleaning VCClient Forge Workspace");
console.log("==========================================\n");

for (const target of targets) {
  cleanPath(target);
}

// Clean any lingering __pycache__ in backend and scripts
cleanPyCache(path.join(projectRoot, "backend"));
cleanPyCache(path.join(projectRoot, "scripts"));

console.log("\n[OK] Clean complete! Workspace is clean and tidy.");
