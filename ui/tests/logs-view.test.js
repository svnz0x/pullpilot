import test from "node:test";
import assert from "node:assert/strict";

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
