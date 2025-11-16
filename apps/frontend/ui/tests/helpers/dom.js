import { resetDomEnvironment } from "../setup-dom.js";
import { buildAppShell } from "./dom-structure.js";

export const setupDom = async () => {
  const window = resetDomEnvironment();
  const { document } = window;
  document.open();
  buildAppShell(document);
  document.close();
  return { window, document };
};
