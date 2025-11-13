import test from "node:test";
import assert from "node:assert/strict";

import { formatLogMetadata } from "../src/app.js";

test("formatLogMetadata muestra 0 bytes para archivos vacíos", () => {
  const text = formatLogMetadata({ logDir: "", modified: "", size: 0 });
  assert.equal(text, "Tamaño: 0 bytes");
});

test("formatLogMetadata evita separadores adicionales cuando faltan datos", () => {
  const text = formatLogMetadata({ logDir: "logs", modified: "", size: undefined });
  assert.equal(text, "Directorio: logs");
});
