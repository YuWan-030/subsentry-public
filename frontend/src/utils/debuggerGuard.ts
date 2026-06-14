const BLOCKED_CTRL_SHIFT_KEYS = new Set(["C", "I", "J"]);
const BLOCKED_CTRL_KEYS = new Set(["S", "U"]);
const PAUSE_THRESHOLD_MS = 160;
const PROBE_INTERVAL_MS = 1200;

let installed = false;
let reloadScheduled = false;
let probeTimer: number | undefined;

const stopEvent = (event: Event) => {
  event.preventDefault();
  event.stopPropagation();
};

const scheduleReload = () => {
  if (reloadScheduled) {
    return;
  }
  reloadScheduled = true;
  window.setTimeout(() => {
    window.location.reload();
  }, 80);
};

const runDebuggerProbe = () => {
  const startedAt = performance.now();
  debugger;
  const pausedFor = performance.now() - startedAt;
  if (pausedFor > PAUSE_THRESHOLD_MS) {
    scheduleReload();
  }
};

export function installDebuggerGuard(enabled = import.meta.env.PROD) {
  if (!enabled || installed || typeof window === "undefined") {
    return;
  }
  installed = true;

  window.addEventListener(
    "keydown",
    (event) => {
      const key = event.key.toUpperCase();
      if (
        key === "F12" ||
        ((event.ctrlKey || event.metaKey) && event.shiftKey && BLOCKED_CTRL_SHIFT_KEYS.has(key)) ||
        ((event.ctrlKey || event.metaKey) && BLOCKED_CTRL_KEYS.has(key))
      ) {
        stopEvent(event);
      }
    },
    true
  );

  window.addEventListener("contextmenu", stopEvent, true);
  probeTimer = window.setInterval(runDebuggerProbe, PROBE_INTERVAL_MS);
  window.addEventListener("beforeunload", () => {
    if (probeTimer !== undefined) {
      window.clearInterval(probeTimer);
    }
  });
}
