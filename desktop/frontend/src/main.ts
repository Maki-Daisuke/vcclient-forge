import { Events } from '@wailsio/runtime';
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
//import { StartupStatus, RetryBackend } from "../bindings/vcclient-forge/desktop/supervisorservice";

// const startup = document.getElementById("startup") as HTMLElement | null;
// const title = document.getElementById("status-title") as HTMLElement | null;
// const message = document.getElementById("message") as HTMLElement | null;
// const retry = document.getElementById("retry") as HTMLButtonElement | null;
const elapsed = document.getElementById("elapsed") as HTMLElement | null;
const terminalContainer = document.getElementById("terminal-container") as HTMLElement | null;

let term: Terminal | null = null;
let fitAddon: FitAddon | null = null;

if (terminalContainer) {
  term = new Terminal({
    fontFamily: '"Cascadia Mono", "Consolas", monospace',
    fontSize: 12,
    lineHeight: 1.4,
    cursorBlink: false,
    disableStdin: true,
    convertEol: true,
    windowsMode: true,
    scrollback: 1000,
    theme: {
      background: "#1a1e1d",
      foreground: "#e2e8e5",
      cursor: "transparent",
      black: "#2d3532",
      red: "#e06c75",
      green: "#98c379",
      yellow: "#e5c07b",
      blue: "#61afef",
      magenta: "#c678dd",
      cyan: "#56b6c2",
      white: "#abb2bf",
      brightBlack: "#5c6370",
      brightRed: "#be5046",
      brightGreen: "#98c379",
      brightYellow: "#d19a66",
      brightBlue: "#61afef",
      brightMagenta: "#c678dd",
      brightCyan: "#56b6c2",
      brightWhite: "#ffffff",
    },
  });

  fitAddon = new FitAddon();
  term.loadAddon(fitAddon);
  term.open(terminalContainer);
  try {
    fitAddon.fit();
  } catch (_) {}

  window.addEventListener("resize", () => {
    try {
      fitAddon?.fit();
    } catch (_) {}
  });

  if (typeof ResizeObserver !== "undefined") {
    const resizeObserver = new ResizeObserver(() => {
      try {
        fitAddon?.fit();
      } catch (_) {}
    });
    resizeObserver.observe(terminalContainer);
  }
}

const startedAt = Date.now();
window.setInterval(() => {
  if (elapsed) {
    elapsed.textContent = `${Math.floor((Date.now() - startedAt) / 1000)}s`;
  }
}, 500);

Events.On("backend-log", (ev) => {
  if (term) {
    term.write(ev.data);
  }
});

Events.On("backend-ready", () => {
  window.location.href = "http://127.0.0.1:18888";
});
