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

test("reset config stays disabled without snapshot and retry flow reloads data", async () => {
  const result = await runWorker(new URL("./reset-config.worker.js", import.meta.url));

  assert.equal(result.failure.resetDisabled, true);
  assert.equal(result.failure.retryVisible, true);
  assert.equal(
    result.failure.summary,
    "Token válido, pero el backend no devolvió la configuración. Revisa el servicio e inténtalo de nuevo.",
  );

  assert.equal(
    result.manualNotice,
    "No hay una configuración cargada para descartar. Usa «Reintentar carga» para intentarlo de nuevo.",
  );

  assert.equal(result.retry.resetEnabled, true);
  assert.equal(result.retry.retryHidden, true);
  assert.equal(result.retry.remainingFetchHandlers, 0);
  assert.equal(result.retry.successSummary, "Configuración cargada correctamente.");
});
