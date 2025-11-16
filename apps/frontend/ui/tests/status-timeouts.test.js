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

test("latest status remains visible until its own timeout", async () => {
  const result = await runWorker(new URL("./status-timeouts.worker.js", import.meta.url));

  assert.equal(result.firstSummary, "Programación cargada correctamente.");
  assert.equal(result.secondSummary, "Se restauró la programación cargada.");
  assert.equal(result.visibleAfterFirstTimer, true);
  assert.equal(result.hiddenAfterSecondTimer, true);
});
