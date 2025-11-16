import { Window } from "happy-dom";
import { buildAppShell } from "./helpers/dom-structure.js";

let activeWindow;

export const resetDomEnvironment = () => {
  if (activeWindow) {
    activeWindow.close();
  }

  const window = new Window({ url: "https://example.test/ui/" });
  activeWindow = window;

  const { document } = window;

  const mappings = {
    window,
    self: window,
    document,
    navigator: window.navigator,
    Node: window.Node,
    HTMLElement: window.HTMLElement,
    Event: window.Event,
    CustomEvent: window.CustomEvent,
    DOMParser: window.DOMParser,
    getComputedStyle: window.getComputedStyle,
    requestAnimationFrame: window.requestAnimationFrame,
    cancelAnimationFrame: window.cancelAnimationFrame,
  };

  for (const [key, value] of Object.entries(mappings)) {
    const descriptor = Object.getOwnPropertyDescriptor(globalThis, key);
    if (descriptor && descriptor.get && !descriptor.set) {
      continue;
    }
    globalThis[key] = value;
  }

  globalThis.localStorage = window.localStorage;
  globalThis.sessionStorage = window.sessionStorage;
  globalThis.fetch = undefined;

  document.open();
  buildAppShell(document);
  document.close();

  return window;
};

resetDomEnvironment();
