/**
 * Frontend Build Stub / Synchronizer
 *
 * Copies the reference web_front assets to frontend/dist as a mock build step
 * until frontend/src is fully re-implemented with modern Vite/React.
 */
const fs = require("fs");
const path = require("path");

const projectRoot = path.resolve(__dirname, "..");
const srcDir = path.join(projectRoot, "web_front");
const destDir = path.join(projectRoot, "frontend", "dist");

if (!fs.existsSync(srcDir)) {
  console.error(`[ERROR] Source directory does not exist: ${srcDir}`);
  process.exit(1);
}

console.log(`[BUILD:FRONTEND] Syncing ${srcDir} -> ${destDir}...`);
fs.rmSync(destDir, { recursive: true, force: true });
fs.cpSync(srcDir, destDir, { recursive: true });
console.log(`[OK] frontend/dist successfully prepared from web_front`);
