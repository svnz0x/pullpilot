import { defineConfig } from "vite";
import { resolve } from "path";

const projectRoot = __dirname;

export default defineConfig({
  root: projectRoot,
  publicDir: false,
  base: "/ui/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    assetsDir: "assets",
    manifest: true,
    rollupOptions: {
      input: resolve(projectRoot, "index.html"),
    },
  },
});
