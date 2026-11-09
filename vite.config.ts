import { defineConfig } from "vite";

// Vite serves and builds the UI from ./ui; Tauri loads ui/dist in release
// and http://localhost:1420 in dev (see src-tauri/tauri.conf.json).
export default defineConfig({
  root: "ui",
  clearScreen: false,
  base: "./",
  server: {
    port: 1420,
    strictPort: true,
    host: "localhost",
    watch: { ignored: ["**/src-tauri/**", "**/engine/**"] },
  },
  envPrefix: ["VITE_", "TAURI_ENV_"],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2021",
    sourcemap: false,
    // The app never loads anything from the network: keep assets inline-able.
    assetsInlineLimit: 100000,
  },
});
