import test from "node:test";
import assert from "node:assert/strict";

import { toggleInitialLoadOnControl } from "../src/app.js";

const createControl = ({ disabled = false, value = "" } = {}) => {
  const control = {
    disabled,
    value,
    dataset: {},
    attributes: {},
    setAttribute(name, attributeValue) {
      this.attributes[name] = attributeValue;
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
  };
  return control;
};

test("toggleInitialLoadOnControl bloquea y restaura controles habilitados", () => {
  const control = createControl({ value: "mi-valor" });

  toggleInitialLoadOnControl(control, true);

  assert.equal(control.disabled, true);
  assert.equal(control.dataset.initialLoadDisabled, "true");
  assert.equal(control.attributes["aria-disabled"], "true");

  toggleInitialLoadOnControl(control, false);

  assert.equal(control.disabled, false);
  assert.equal(Object.prototype.hasOwnProperty.call(control.dataset, "initialLoadDisabled"), false);
  assert.equal(Object.prototype.hasOwnProperty.call(control.dataset, "initialLoadWasDisabled"), false);
  assert.equal(control.attributes["aria-disabled"], undefined);
  assert.equal(control.value, "mi-valor");
});

test("toggleInitialLoadOnControl respeta controles que ya estaban deshabilitados", () => {
  const control = createControl({ disabled: true });

  toggleInitialLoadOnControl(control, true);

  assert.equal(control.disabled, true);
  assert.equal(control.dataset.initialLoadWasDisabled, "true");

  toggleInitialLoadOnControl(control, false);

  assert.equal(control.disabled, true);
  assert.equal(control.attributes["aria-disabled"], "true");
});

test("toggleInitialLoadOnControl no descarta cambios locales en el valor", () => {
  const control = createControl({ value: "original" });

  toggleInitialLoadOnControl(control, true);
  control.value = "editado-por-el-usuario";
  toggleInitialLoadOnControl(control, false);

  assert.equal(control.value, "editado-por-el-usuario");
});

