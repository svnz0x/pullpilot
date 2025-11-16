import test from "node:test";
import assert from "node:assert/strict";
import { runWorker } from "./helpers/run-worker.js";

test("latest status remains visible until its own timeout", async () => {
  const result = await runWorker(new URL("./status-timeouts.worker.js", import.meta.url));

  assert.equal(result.firstSummary, "Programación cargada correctamente.");
  assert.equal(result.secondSummary, "Se restauró la programación cargada.");
  assert.equal(result.visibleAfterFirstTimer, true);
  assert.equal(result.hiddenAfterSecondTimer, true);
});
