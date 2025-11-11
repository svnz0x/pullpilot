import { defineConfig } from "vite";
import { resolve } from "path";

const uiRoot = resolve(__dirname, "src/pullpilot/resources/ui");

export default defineConfig({
  root: uiRoot,
  publicDir: false,
  base: "/ui/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    assetsDir: "assets",
    manifest: true,
    rollupOptions: {
      input: resolve(uiRoot, "index.html"),
    },
  },
});
