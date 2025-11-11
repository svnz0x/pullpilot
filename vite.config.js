import { defineConfig } from "vite";
import { resolve } from "path";

const uiRoot = resolve(__dirname, "ui");

export default defineConfig({
  root: uiRoot,
  publicDir: false,
  base: "/ui/",
  build: {
    outDir: "../src/pullpilot/resources/ui/dist",
    emptyOutDir: true,
    assetsDir: "assets",
    manifest: true,
    rollupOptions: {
      input: resolve(uiRoot, "index.html"),
    },
  },
});
