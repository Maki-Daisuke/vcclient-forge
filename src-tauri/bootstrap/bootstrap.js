"use strict";

const startup = document.getElementById("startup");
const title = document.getElementById("status-title");
const message = document.getElementById("message");
const logs = document.getElementById("logs");
const retry = document.getElementById("retry");
const elapsed = document.getElementById("elapsed");
let startedAt = Date.now();
let refreshing = false;

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const status = await window.__TAURI__.core.invoke("startup_status");
    document.body.dataset.phase = status.phase;
    startup.setAttribute("aria-busy", String(status.phase === "starting"));
    title.textContent =
      status.phase === "failed"
        ? "Connection failed"
        : status.phase === "ready"
          ? "Connected"
          : "Starting backend";
    message.textContent = status.message;
    const followLogs =
      logs.scrollHeight - logs.scrollTop - logs.clientHeight <= 24;
    logs.textContent = status.logs.join("\n") || "Waiting for backend output.";
    if (followLogs) logs.scrollTop = logs.scrollHeight;
    retry.hidden = status.phase !== "failed";
    elapsed.textContent = `${Math.floor((Date.now() - startedAt) / 1000)}s`;
  } catch (error) {
    title.textContent = "Desktop connection unavailable";
    message.textContent = String(error);
    startup.setAttribute("aria-busy", "false");
    document.body.dataset.phase = "failed";
  } finally {
    refreshing = false;
  }
}

retry.addEventListener("click", async () => {
  retry.disabled = true;
  try {
    await window.__TAURI__.core.invoke("retry_backend");
    startedAt = Date.now();
    await refresh();
  } catch (error) {
    message.textContent = String(error);
  } finally {
    retry.disabled = false;
  }
});

void refresh();
window.setInterval(() => void refresh(), 500);
