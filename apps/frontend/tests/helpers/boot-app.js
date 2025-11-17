import { setupDom } from "./dom.js";

let importCounter = 0;

export const bootApp = async ({ fetchMock } = {}) => {
  const { window } = await setupDom();

  if (fetchMock) {
    globalThis.fetch = fetchMock;
  } else if (!globalThis.fetch) {
    globalThis.fetch = () => {
      throw new Error("Fetch mock not configured");
    };
  }

  importCounter += 1;
  const moduleUrl = new URL(`../../src/app.js?test-instance=${importCounter}`, import.meta.url);
  await import(moduleUrl);
  return window;
};
