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

test("missing credentials response keeps token according to remember option", async () => {
  const result = await runWorker(
    new URL("./login-missing-credentials.worker.js", import.meta.url),
  );

  assert.equal(result.rememberResult.local, result.tokenValue);
  assert.equal(result.rememberResult.session, null);
  assert.equal(result.forgetResult.local, null);
  assert.equal(result.forgetResult.session, null);
});
