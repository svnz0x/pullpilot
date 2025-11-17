export const installMockTimers = () => {
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;

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
    const entry = {
      callback: (...invokeArgs) => callbackFn(...invokeArgs),
      args,
      time: currentTime + (targetDelay < 0 ? 0 : targetDelay),
    };
    timers.set(id, entry);
    return id;
  };

  const cancelTimer = (id) => {
    timers.delete(id);
  };

  const flushWith = async (callback) => {
    const promise = callback();
    advanceTimersBy(0);
    await promise;
  };

  globalThis.setTimeout = scheduleTimer;
  globalThis.clearTimeout = cancelTimer;

  const restore = () => {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  };

  return { advanceTimersBy, flushWith, restore };
};
