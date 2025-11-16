import test from "node:test";
import assert from "node:assert/strict";
import { Worker } from "node:worker_threads";

import {
  createLogsRequestManager,
  formatLogMetadata,
  resolveLogContentText,
} from "../src/app.js";

test("formatLogMetadata muestra 0 bytes para archivos vacíos", () => {
  const text = formatLogMetadata({ logDir: "", modified: "", size: 0 });
  assert.equal(text, "Tamaño: 0 bytes");
});

test("formatLogMetadata evita separadores adicionales cuando faltan datos", () => {
  const text = formatLogMetadata({ logDir: "logs", modified: "", size: undefined });
  assert.equal(text, "Directorio: logs");
});

test("resolveLogContentText muestra visor vacío cuando content es cadena vacía", () => {
  const text = resolveLogContentText({ name: "app.log", content: "" });
  assert.equal(text, "");
});

test("createLogsRequestManager mantiene la última selección aunque las respuestas lleguen tarde", () => {
  const manager = createLogsRequestManager();

  const first = manager.start();
  const second = manager.start();

  let renderedSelection = null;

  const renderIfLatest = (request, selection) => {
    if (manager.isLatest(request.id)) {
      renderedSelection = selection;
    }
  };

  // La segunda respuesta llega primero y debe fijar la selección.
  renderIfLatest(second, "segundo.log");
  // La primera respuesta llega al final, pero debe ignorarse.
  renderIfLatest(first, "primero.log");

  if (first.controller) {
    assert.equal(first.controller.signal.aborted, true);
  }
  if (second.controller) {
    assert.equal(second.controller.signal.aborted, false);
  }

  assert.equal(renderedSelection, "segundo.log");
});

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

test(
  "la vista de logs conserva la selección tras un error de red y bloquea las acciones en curso",
  async () => {
    const result = await runWorker(new URL("./logs-view.worker.js", import.meta.url));

    assert.deepEqual(result.optionsAfter, result.optionsBefore);
    assert.equal(result.selectionAfter, result.selectionBefore);
    assert.equal(result.contentAfter, result.contentBefore);
    assert.equal(result.metaAfter, result.metaBefore);
    assert.equal(result.logsStatusText, "No se pudieron cargar los logs.");
    assert.equal(result.refreshDisabledDuringRequest, true);
    assert.equal(result.refreshDisabled, false);
    assert.equal(result.contentDuringRefresh, "Cargando logs…");
    assert.equal(result.selectDisabledDuringRefresh, true);
    assert.equal(result.selectBusyDuringRefresh, "true");
    assert.equal(result.contentBusyDuringRefresh, "true");
    assert.equal(result.selectBusyAfter, null);
    assert.equal(result.contentBusyAfter, null);
    assert.equal(result.scheduleButtons.before.saveDisabled, false);
    assert.equal(result.scheduleButtons.during.saveDisabled, true);
    assert.equal(result.scheduleButtons.after.saveDisabled, false);
    assert.equal(result.scheduleButtons.before.resetDisabled, false);
    assert.equal(result.scheduleButtons.during.resetDisabled, true);
    assert.equal(result.scheduleButtons.after.resetDisabled, false);
    assert.equal(result.scheduleButtons.before.formBusy, null);
    assert.equal(result.scheduleButtons.during.formBusy, "true");
    assert.equal(result.scheduleButtons.after.formBusy, null);
    assert.equal(result.remainingFetchHandlers, 0);
  },
);
