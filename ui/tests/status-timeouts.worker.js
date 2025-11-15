import { parentPort } from "node:worker_threads";

let currentTime = 0;
let nextTimerId = 1;
const timers = new Map();

const runDueTimers = () => {
  while (true) {
    const dueEntries = Array.from(timers.entries())
      .filter(([, entry]) => entry.time <= currentTime)
      .sort((a, b) => {
        if (a[1].time === b[1].time) {
          return a[0] - b[0];
        }
        return a[1].time - b[1].time;
      });
    if (dueEntries.length === 0) {
      break;
    }
    for (const [id, entry] of dueEntries) {
      timers.delete(id);
      entry.callback(...entry.args);
    }
  }
};

const advanceTimersBy = (milliseconds) => {
  if (typeof milliseconds === "number" && milliseconds > 0) {
    currentTime += milliseconds;
  }
  runDueTimers();
};

const scheduleTimer = (callback, delay = 0, ...args) => {
  const id = nextTimerId++;
  const targetDelay = typeof delay === "number" ? delay : Number(delay) || 0;
  const callbackFn = typeof callback === "function" ? callback : new Function(callback);
  const timerEntry = {
    callback: (...invokeArgs) => callbackFn(...invokeArgs),
    args,
    time: currentTime + (targetDelay < 0 ? 0 : targetDelay),
  };
  timers.set(id, timerEntry);
  return id;
};

const cancelTimer = (id) => {
  timers.delete(id);
};

globalThis.setTimeout = scheduleTimer;
globalThis.clearTimeout = cancelTimer;

globalThis.__advanceTimersBy = advanceTimersBy;

globalThis.__flushTimers = async (flush) => {
  const promise = flush();
  advanceTimersBy(0);
  await promise;
};

const { createAppTestHarness } = await import("./helpers/app-harness.js");

const {
  loginForm,
  tokenInput,
  scheduleStatus,
  scheduleReset,
  enqueueResponses,
  okResponse,
  flush,
  FakeEvent,
} = createAppTestHarness();

const flushWithTimers = async () => {
  await globalThis.__flushTimers(flush);
};

const authCheckResponse = () => Promise.resolve(new Response(null, { status: 204 }));

const configPayload = {
  schema: {
    variables: [],
  },
  values: {
    BASE_DIR: "/srv/app",
    LOG_DIR: "/srv/app/logs",
  },
};

const schedulePayload = { mode: "cron", expression: "0 0 * * *", datetime: "" };
const logsPayload = { files: [], selected: null, log_dir: "" };

enqueueResponses([
  authCheckResponse,
  () => okResponse(configPayload),
  () => okResponse(schedulePayload),
  () => okResponse(logsPayload),
]);

await import(new URL("../src/app.js", import.meta.url));

tokenInput.value = "demo-token";
loginForm.dispatchEvent(new FakeEvent("submit", { bubbles: true, cancelable: true }));

await flushWithTimers();
await flushWithTimers();
await flushWithTimers();

let initialSummary = scheduleStatus.querySelector("span")?.textContent ?? "";
let attempts = 0;
while (initialSummary !== "Programación cargada correctamente." && attempts < 5) {
  await flushWithTimers();
  initialSummary = scheduleStatus.querySelector("span")?.textContent ?? "";
  attempts += 1;
}

const firstSummary = initialSummary;

advanceTimersBy(100);

scheduleReset.dispatchEvent(new FakeEvent("click", { bubbles: true, cancelable: true }));

const secondSummary = scheduleStatus.querySelector("span")?.textContent ?? "";

advanceTimersBy(2401);

const visibleAfterFirstTimer = scheduleStatus.hidden === false;

advanceTimersBy(200);

const hiddenAfterSecondTimer = scheduleStatus.hidden === true;

parentPort.postMessage({
  firstSummary,
  secondSummary,
  visibleAfterFirstTimer,
  hiddenAfterSecondTimer,
});
