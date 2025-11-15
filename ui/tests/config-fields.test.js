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

test("config fields expose HTML constraints and block invalid values", async () => {
  const result = await runWorker(new URL("./config-fields.worker.js", import.meta.url));

  assert.equal(result.lockField.pattern, "^/.*");
  assert.equal(result.lockField.required, true);
  assert.equal(result.lockField.ariaRequired, "true");

  assert.equal(result.retentionField.min, "1");
  assert.equal(result.retentionField.hasErrorClass, true);

  assert.equal(result.validation.remainingFetchHandlers, 1);
  assert.equal(result.validation.summary, "Revisa los campos marcados antes de guardar.");
  assert.equal(
    result.validation.firstDetail,
    "LOG_RETENTION_DAYS: Debe ser como mínimo 1.",
  );
});
