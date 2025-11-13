import test from "node:test";
import assert from "node:assert/strict";
import { Worker } from "node:worker_threads";

const runWorker = (url) =>
  new Promise((resolve, reject) => {
    const worker = new Worker(url, { type: "module" });
    worker.once("message", resolve);
    worker.once("error", reject);
    worker.once("exit", (code) => {
      if (code !== 0) {
        reject(new Error(`Worker exited with code ${code}`));
      }
    });
  });

test("unauthorized flow keeps persisted token and checkbox checked", async () => {
  const result = await runWorker(new URL("./handle-unauthorized.worker.js", import.meta.url));
  assert.equal(result.checkboxAfterUnauthorized, true);
  assert.equal(result.tokenInputAfterUnauthorized, result.tokenValue);
  assert.equal(result.storedAfterUnauthorized, result.tokenValue);
  assert.equal(result.storedAfterRelogin, result.tokenValue);
});
